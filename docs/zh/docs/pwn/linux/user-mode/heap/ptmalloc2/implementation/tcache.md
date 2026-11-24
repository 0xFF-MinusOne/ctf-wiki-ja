# tcache

tcache は glibc 2.26(ubuntu 17.10)以降で導入された技術です(see [commit](https://sourceware.org/git/?p=glibc.git;a=commitdiff;h=d5c3fafc4307c9b7a4c7d5cb381fcdbfad340bcc))。ヒープ管理の性能を高めることを目的としています。しかし、性能向上と引き換えに多くのセキュリティチェックが省かれたため、新たな悪用方法がたくさん生まれました。

> 主に glibc のソースコード、angelboy のスライド、tukan.farm を参考にしました。リンクは最後にまとめてあります。

## 関連する構造体

tcache では、`tcache_entry` と `tcache_perthread_struct` という2つの新しい構造体が導入されました。

これは実は fastbin とよく似ていますが、同じではありません。

### tcache_entry

[source code](https://code.woboq.org/userspace/glibc/malloc/malloc.c.html#tcache_entry)

```C
/* We overlay this structure on the user-data portion of a chunk when
   the chunk is stored in the per-thread cache.  */
typedef struct tcache_entry
{
  struct tcache_entry *next;
} tcache_entry;
```

`tcache_entry` は空きチャンクの構造体をつなぐためのもので、中の `next` ポインタは同じサイズの次のチャンクを指します。

ここで注意すべきなのは、next がチャンクの user data を指すのに対し、fastbin の fd はチャンクの先頭のアドレスを指す点です。

また、tcache_entry は空きチャンクの user data 部分を再利用します。

### tcache_perthread_struct

[source code](https://code.woboq.org/userspace/glibc/malloc/malloc.c.html#tcache_perthread_struct)
```C
/* There is one of these for each thread, which contains the
   per-thread cache (hence "tcache_perthread_struct").  Keeping
   overall size low is mildly important.  Note that COUNTS and ENTRIES
   are redundant (we could have just counted the linked list each
   time), this is for performance reasons.  */
typedef struct tcache_perthread_struct
{
  char counts[TCACHE_MAX_BINS];
  tcache_entry *entries[TCACHE_MAX_BINS];
} tcache_perthread_struct;

# define TCACHE_MAX_BINS                64

static __thread tcache_perthread_struct *tcache = NULL;
```

各スレッドは `tcache_perthread_struct` を1つずつ保持します。これは tcache 全体の管理構造で、`TCACHE_MAX_BINS` 個のカウンタと `TCACHE_MAX_BINS` 個の tcache_entry を持ちます。それぞれの役割は次のとおりです。

- `tcache_entry` は、同じサイズの空き状態(free 後)のチャンクを単方向リストでつなぎます。この点は fastbin とよく似ています。
- `counts` は `tcache_entry` のリスト上にある空きチャンクの数を記録します。各リストには最大 7 個のチャンクを置けます。

図で表すとおおよそ次のようになります。

![](https://i0.wp.com/tvax1.sinaimg.cn/large/006AWYXBly1fw87zlnrhtj30nh0ciglz.jpg)


## 基本的な動作

- 最初の malloc では、まず `tcache_perthread_struct` を格納するためのメモリを malloc します。
- メモリを free し、size が small bin のサイズ未満のとき
  - tcache 導入前は fastbin または unsorted bin に入れられていました
  - tcache 導入後:
    - まず対応する tcache に入れ、tcache がいっぱいになる(デフォルトは 7 個)まで続けます
    - tcache がいっぱいになった後に free したメモリは、従来どおり fastbin または unsorted bin に入れられます
    - tcache 内のチャンクは統合(consolidation)されません(inuse bit を落としません)
- メモリを malloc し、size が tcache の範囲内のとき
  - まず tcache からチャンクを取り出し、tcache が空になるまで続けます
  - tcache が空になったら bin から探します
  - tcache が空のとき、`fastbin/smallbin/unsorted bin` に size が合致するチャンクがあれば、まず `fastbin/smallbin/unsorted bin` のチャンクを tcache がいっぱいになるまで tcache に移します。その後、tcache から取り出します。そのため、チャンクの順序は bin 内と tcache 内で逆になります

## ソースコード解析

ここからは、ソースコードの観点から tcache を解析します。

### __libc_malloc
最初の malloc では `MAYBE_INIT_TCACHE ()` に入ります。

[source code](https://code.woboq.org/userspace/glibc/malloc/malloc.c.html#3010)
```C
void *
__libc_malloc (size_t bytes)
{
    ......
    ......
#if USE_TCACHE
  /* int_free also calls request2size, be careful to not pad twice.  */
  size_t tbytes;
  // malloc に渡された引数からチャンクの実際のサイズを計算し、tcache に対応するインデックスを計算する
  checked_request2size (bytes, tbytes);
  size_t tc_idx = csize2tidx (tbytes);

  // tcache を初期化する
  MAYBE_INIT_TCACHE ();
  DIAG_PUSH_NEEDS_COMMENT;
  if (tc_idx < mp_.tcache_bins  // size から得た idx が正当な範囲内にある
      /*&& tc_idx < TCACHE_MAX_BINS*/ /* to appease gcc */
      && tcache
      && tcache->entries[tc_idx] != NULL) // tcache->entries[tc_idx] にチャンクがある
    {
      return tcache_get (tc_idx);
    }
  DIAG_POP_NEEDS_COMMENT;
#endif
    ......
    ......
}
```

### __tcache_init()
このうち `MAYBE_INIT_TCACHE ()` は、tcache が空(つまり最初の malloc)のときに `tcache_init()` を呼び出します。そこで `tcache_init()` を直接見てみましょう。

[source code](https://code.woboq.org/userspace/glibc/malloc/malloc.c.html#tcache_init)

```C
tcache_init(void)
{
  mstate ar_ptr;
  void *victim = 0;
  const size_t bytes = sizeof (tcache_perthread_struct);
  if (tcache_shutting_down)
    return;
  arena_get (ar_ptr, bytes); // 利用可能な arena を探す
  victim = _int_malloc (ar_ptr, bytes); // sizeof(tcache_perthread_struct) のサイズのチャンクを確保する
  if (!victim && ar_ptr != NULL)
    {
      ar_ptr = arena_get_retry (ar_ptr, bytes);
      victim = _int_malloc (ar_ptr, bytes);
    }
  if (ar_ptr != NULL)
    __libc_lock_unlock (ar_ptr->mutex);
  /* In a low memory situation, we may not be able to allocate memory
     - in which case, we just keep trying later.  However, we
     typically do this very early, so either there is sufficient
     memory, or there isn't enough memory to do non-trivial
     allocations anyway.  */
  if (victim) // tcache を初期化する
    {
      tcache = (tcache_perthread_struct *) victim;
      memset (tcache, 0, sizeof (tcache_perthread_struct));
    }
}
```

`tcache_init()` が正常に戻ると、`tcache_perthread_struct` の作成は成功しています。

### メモリの確保
次に、メモリを確保するステップに進みます。
```C
  // tcache list からメモリを取得する
  if (tc_idx < mp_.tcache_bins // size から計算した idx が正当な範囲内にある
      /*&& tc_idx < TCACHE_MAX_BINS*/ /* to appease gcc */
      && tcache
      && tcache->entries[tc_idx] != NULL) // その tcache のリストが空でない
    {
      return tcache_get (tc_idx);
    }
  DIAG_POP_NEEDS_COMMENT;
#endif
  // tcache がない場合と似た流れに入る
  if (SINGLE_THREAD_P)
    {
      victim = _int_malloc (&main_arena, bytes);
      assert (!victim || chunk_is_mmapped (mem2chunk (victim)) ||
              &main_arena == arena_for_chunk (mem2chunk (victim)));
      return victim;
    }

```
`tcache->entries` が空でないときは `tcache_get()` の流れに入ってチャンクを取得し、そうでなければ tcache 機構導入前と似た流れになります。ここでは主に前者の `tcache_get()` を解析します。ここから、tcache の優先度が非常に高く、fastbin よりも高いことも分かります(fastbin からの確保は、tcache の流れに入らなかった場合に行われます)。

### tcache_get()
`tcache_get()` を見てみましょう。

[source code](https://code.woboq.org/userspace/glibc/malloc/malloc.c.html#tcache_get)
```C
/* Caller must ensure that we know tc_idx is valid and there's
   available chunks to remove.  */
static __always_inline void *
tcache_get (size_t tc_idx)
{
  tcache_entry *e = tcache->entries[tc_idx];
  assert (tc_idx < TCACHE_MAX_BINS);
  assert (tcache->entries[tc_idx] > 0);
  tcache->entries[tc_idx] = e->next;
  --(tcache->counts[tc_idx]); // チャンクを1つ取得したので counts を1減らす
  return (void *) e;
}
```
`tcache_get()` がチャンクを取得する処理です。この処理は非常に単純で、`tcache->entries[tc_idx]` の先頭のチャンクを取得して `tcache->counts` を1減らすだけであり、保護はほとんどありません。

### __libc_free()
確保を見終えたので、次は tcache がある場合の解放を見てみましょう。

[source code](https://code.woboq.org/userspace/glibc/malloc/malloc.c.html#3068)
```C
void
__libc_free (void *mem)
{
  ......
  ......
  MAYBE_INIT_TCACHE ();
  ar_ptr = arena_for_chunk (p);
  _int_free (ar_ptr, p, 0);
}
```
`__libc_free()` に大きな変化はありません。tcache が空でない場合、`MAYBE_INIT_TCACHE ()` は意味を失います。

### _int_free()
`_int_free()` に進みます。

[source code](https://code.woboq.org/userspace/glibc/malloc/malloc.c.html#4123)
```C
static void
_int_free (mstate av, mchunkptr p, int have_lock)
{
  ......
  ......
#if USE_TCACHE
  {
    size_t tc_idx = csize2tidx (size);
    if (tcache
        && tc_idx < mp_.tcache_bins // 64
        && tcache->counts[tc_idx] < mp_.tcache_count) // 7
      {
        tcache_put (p, tc_idx);
        return;
      }
  }
#endif
  ......
  ......
```
`tc_idx` が正当で、`tcache->counts[tc_idx]` が 7 個以内のとき、`tcache_put()` に入ります。渡される2つの引数は、解放するチャンクと、そのチャンクの size に対応する tcache 内のインデックスです。


### tcache_put()

[source code](https://code.woboq.org/userspace/glibc/malloc/malloc.c.html#2907)

```C
/* Caller must ensure that we know tc_idx is valid and there's room
   for more chunks.  */
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
`tcache_puts()` は、解放されたチャンクを `tcache->entries[tc_idx]` のリストの先頭に挿入する処理を行います。こちらもほとんど保護がありません。しかも、**p のビットをクリアしません**。



## 参考

- http://tukan.farm/2017/07/08/tcache/
- https://github.com/bash-c/slides/blob/master/pwn_heap/tcache_exploitation.pdf
- https://www.secpulse.com/archives/71958.html
