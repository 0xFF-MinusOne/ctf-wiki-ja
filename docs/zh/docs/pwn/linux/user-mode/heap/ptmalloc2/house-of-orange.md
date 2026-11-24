# House of Orange


## はじめに

House of Orange は、ほかの House of XX 系の攻撃手法とは異なり、Hitcon CTF 2016 の同名の問題に由来します。この手法はそれ以前の CTF の問題には登場していなかったため、その後に現れた一連の派生問題の攻略手法を House of Orange と呼んでいます。

## 概要

House of Orange の利用は少し特殊です。まず、対象の脆弱性はヒープ上の脆弱性であることが必要ですが、特殊なのは、問題中に free 関数やその他のヒープチャンクを解放する関数が存在しないことです。一般にヒープの脆弱性を悪用するには、ヒープチャンクに対する malloc と free の操作が必要ですが、House of Orange では free 関数を使えません。そのため House of Orange の核心は、脆弱性を利用して free と同じ効果を得ることにあります。


## 原理

前述のとおり、House of Orange の核心は、free 関数がない状況で解放済みのヒープチャンク(unsorted bin)を得ることです。
この操作の原理を簡単に言うと、現在のヒープの top chunk のサイズが要求された確保サイズを満たせないとき、元の top chunk が解放されて unsorted bin に入れられるため、これを利用すれば free 関数なしで unsorted bin を得られるというものです。

この過程を詳しく見てみましょう。現在の top chunk がすでに malloc の確保要求を満たせないとします。
まず、プログラム中の `malloc` 呼び出しは libc.so の `_int_malloc` 関数に到達します。`_int_malloc` 関数では、fastbin、small bins、unsorted bin、large bins の順に確保要求を満たせるかを調べますが、サイズの問題でどれも該当しません。次に `_int_malloc` 関数は top chunk を使おうとしますが、ここでも top chunk は確保要求を満たせないため、次の分岐が実行されます。

```
/*
Otherwise, relay to handle system-dependent cases
*/
else {
      void *p = sysmalloc(nb, av);
      if (p != NULL && __builtin_expect (perturb_byte, 0))
	    alloc_perturb (p, bytes);
      return p;
}
```

この時点で ptmalloc はユーザーのヒープメモリ要求を満たせなくなっており、sysmalloc を実行してシステムからさらに領域を要求する必要があります。
ただし、ヒープには mmap と brk の 2 つの確保方式があり、ヒープが brk の形で拡張されるようにする必要があります。その後、元の top chunk は unsorted bin に置かれます。

まとめると、brk で top chunk を拡張させたいのですが、そのためには libc のいくつかの検査を回避する必要があります。
まず、malloc のサイズは `mp_.mmap_threshold` より大きくてはいけません。

```
if ((unsigned long)(nb) >= (unsigned long)(mp_.mmap_threshold) && (mp_.n_mmaps < mp_.n_mmaps_max))
```

確保しようとする chunk のサイズが mmap による確保のしきい値(デフォルトは 128K)より大きく、かつ現在のプロセスが mmap() で確保したメモリブロックの数が設定された最大値より少ない場合は、mmap() システムコールを使って OS から直接メモリを要求します。

sysmalloc 関数には、次のような top chunk の size に対する検査があります。

```
assert((old_top == initial_top(av) && old_size == 0) ||
	 ((unsigned long) (old_size) >= MINSIZE &&
	  prev_inuse(old_top) &&
	  ((unsigned long)old_end & pagemask) == 0));
```
ここでは top chunk の正当性を検査しています。この関数が初めて呼ばれる場合、top chunk は初期化されていない可能性があり、old_size が 0 になることがあります。
top chunk がすでに初期化されている場合、top chunk のサイズは MINSIZE 以上でなければなりません。top chunk には fencepost が含まれているため、top chunk のサイズは MINSIZE 以上である必要があるのです。次に、top chunk は直前の chunk が inuse 状態であることを示していなければならず、top chunk の終端アドレスは必ずページにアラインされていなければなりません。さらに、top chunk から fencepost を除いたサイズは、要求された chunk のサイズより必ず小さくなければなりません。そうでなければ、_int_malloc() 関数で top chunk から chunk が切り出されてしまいます。

偽造する top chunk の size に対する要件をまとめます。

1. 偽造する size はメモリページにアラインされていなければならない
2. size は MINSIZE(32 ビットでは通常 0x10、64 ビットでは通常 0x20)より大きい
3. size は、その後に要求する chunk のサイズ + MINSIZE(0x10) より小さい
4. size の prev inuse ビットは 1 でなければならない

その後、元の top chunk は `_int_free` を実行され、無事に unsorted bin に入ります。


## 例

ここでは、top chunk の size フィールドにオーバーフローで上書きが及ぶ状況を模したサンプルプログラムを示します。size を小さくして brk による拡張を実現し、元の top chunk を unsorted bin に入れることを試みます。

```
#include <stdlib.h>
#define fake_size 0x41

int main(void)
{
    void *ptr;
    
    ptr=malloc(0x10);
    ptr=(void *)((long long)ptr+24);
    
    *((long long*)ptr)=fake_size; // overwrite top chunk size
    
    malloc(0x60);
    
    malloc(0x60);
}
```
ここでは top chunk の size を 0x41 で上書きしています。その後、このサイズより大きいヒープチャンク、つまり 0x60 を要求します。
しかしこの例を実行すると、assert が満たされず例外が投げられるため、攻撃が成功しないことがわかります。

```
[#0] 0x7ffff7a42428 → Name: __GI_raise(sig=0x6)
[#1] 0x7ffff7a4402a → Name: __GI_abort()
[#2] 0x7ffff7a8a2e8 → Name: __malloc_assert(assertion=0x7ffff7b9e150 "(old_top == initial_top (av) && old_size == 0) || ((unsigned long) (old_size) >= MINSIZE && prev_inuse (old_top) && ((unsigned long) old_end & (pagesize - 1)) == 0)", file=0x7ffff7b9ab85 "malloc.c", line=0x95a, function=0x7ffff7b9e998 <__func__.11509> "sysmalloc")
[#3] 0x7ffff7a8e426 → Name: sysmalloc(nb=0x70, av=0x7ffff7dd1b20 <main_arena>)
```


## 正しい例

assert の条件を振り返ると、先に挙げた項目は最初の 1 つを除いてすべて満たされていることがわかります。

```
1.伪造的size必须要对齐到内存页
```

メモリページにアラインされているとはどういうことでしょうか。現代の OS はメモリページを単位としてメモリを管理しており、一般的なメモリページのサイズは 4kb です。したがって、偽造する size もこの大きさにアラインされていなければなりません。上書き前の top chunk の size は 20fe1 で、計算すると 0x602020+0x20fe0=0x623000 は 0x1000(4kb) にアラインされています。

```
0x602000:	0x0000000000000000	0x0000000000000021
0x602010:	0x0000000000000000	0x0000000000000000
0x602020:	0x0000000000000000	0x0000000000020fe1 <== top chunk
0x602030:	0x0000000000000000	0x0000000000000000
```
したがって、偽造する fake_size は 0x0fe1、0x1fe1、0x2fe1、0x3fe1 など、4kb にアラインされた size であればかまいません。一方、0x40 はアラインされていないため、攻撃は成立しません。

```
#include <stdlib.h>
#define fake_size 0x1fe1

int main(void)
{
    void *ptr;
    
    ptr=malloc(0x10);
    ptr=(void *)((long long)ptr+24);
    
    *((long long*)ptr)=fake_size;
    
    malloc(0x2000);
    
    malloc(0x60);
}
```

確保を行うと、元のヒープが brk によって拡張されたことが観察できます。

```
//元のヒープ
0x0000000000602000 0x0000000000623000 0x0000000000000000 rw- [heap]

//拡張されたヒープ
0x0000000000602000 0x0000000000646000 0x0000000000000000 rw- [heap]
```

要求は 0x623010 の位置に割り当てられ、同時に元のヒープは unsorted bin に入れられます。

```
[+] unsorted_bins[0]: fw=0x602020, bk=0x602020
 →   Chunk(addr=0x602030, size=0x1fc0, flags=PREV_INUSE)
```

unsorted bin にチャンクが存在するため、次の確保ではこのチャンクが切り出されます。

```
 malloc(0x60);
 0x602030

[+] unsorted_bins[0]: fw=0x602090, bk=0x602090
 →   Chunk(addr=0x6020a0, size=0x1f50, flags=PREV_INUSE)
```

確保されたメモリが unsorted bin から切り出されたことがわかります。メモリレイアウトは次のとおりです。

```
0x602030:	0x00007ffff7dd2208	0x00007ffff7dd2208 <== 未被清零的unsorted bin链表
0x602040:	0x0000000000602020	0x0000000000602020
0x602050:	0x0000000000000000	0x0000000000000000
0x602060:	0x0000000000000000	0x0000000000000000
0x602070:	0x0000000000000000	0x0000000000000000
0x602080:	0x0000000000000000	0x0000000000000000
0x602090:	0x0000000000000000	0x0000000000001f51 <== 切割剩下的新unsorted bin
0x6020a0:	0x00007ffff7dd1b78	0x00007ffff7dd1b78
0x6020b0:	0x0000000000000000	0x0000000000000000

```


実は house of orange の要点はここにあり、その後の攻撃は _IO_FILE の知識に関わるため、IO_FILE の独立した章で紹介します。
