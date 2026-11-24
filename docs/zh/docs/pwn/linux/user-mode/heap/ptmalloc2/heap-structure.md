# ヒープ関連のデータ構造

ヒープの操作はこれほど複雑ですから、glibc の内部にも、それを管理するために丹念に設計されたデータ構造があるはずです。ヒープに対応するデータ構造は、主に次の2つに分けられます。

- マクロ構造(macro structure)。ヒープの全体的な情報を含み、これらのデータ構造を通じてヒープの基本情報を引けます。
- ミクロ構造(micro structure)。ヒープの割り当てと回収における個々のメモリブロックを具体的に扱うために使います。

## Overview

> 追記予定です。

## ミクロ構造

ここではまず、ヒープの主な内部構造をいくつか紹介します。**ヒープの脆弱性攻撃は、これらの構造と密接に関係しています**。

### malloc_chunk

#### 概要

プログラムの実行中、malloc で確保したメモリを `chunk` と呼びます。このメモリは ptmalloc の内部では malloc_chunk 構造体で表されます。プログラムが確保した `chunk` が free されると、対応する空きリスト(free list)に追加されます。

非常に興味深いことに、**`chunk` のサイズがどうであれ、また確保状態か解放状態かにかかわらず、すべて同じ1つの構造を使います**。同じデータ構造を使いますが、解放されているかどうかによって、現れ方は異なります。

malloc_chunk の構造は次のとおりです。

```c
/*
  This struct declaration is misleading (but accurate and necessary).
  It declares a "view" into memory allowing access to necessary
  fields at known offsets from a given base. See explanation below.
*/
struct malloc_chunk {

  INTERNAL_SIZE_T      prev_size;  /* Size of previous chunk (if free).  */
  INTERNAL_SIZE_T      size;       /* Size in bytes, including overhead. */

  struct malloc_chunk* fd;         /* double links -- used only if free. */
  struct malloc_chunk* bk;

  /* Only used for large blocks: pointer to next larger size.  */
  struct malloc_chunk* fd_nextsize; /* double links -- used only if free. */
  struct malloc_chunk* bk_nextsize;
};
```

まず、必要なマクロの定義をいくつか示します。

```c
/* INTERNAL_SIZE_T is the word-size used for internal bookkeeping of
   chunk sizes.
   The default version is the same as size_t.
   While not strictly necessary, it is best to define this as an
   unsigned type, even if size_t is a signed type. This may avoid some
   artificial size limitations on some systems.
   On a 64-bit machine, you may be able to reduce malloc overhead by
   defining INTERNAL_SIZE_T to be a 32 bit `unsigned int' at the
   expense of not being able to handle more than 2^32 of malloced
   space. If this limitation is acceptable, you are encouraged to set
   this unless you are on a platform requiring 16byte alignments. In
   this case the alignment requirements turn out to negate any
   potential advantages of decreasing size_t word size.
   Implementors: Beware of the possible combinations of:
     - INTERNAL_SIZE_T might be signed or unsigned, might be 32 or 64 bits,
       and might be the same width as int or as long
     - size_t might have different width and signedness as INTERNAL_SIZE_T
     - int and long might be 32 or 64 bits, and might be the same width
   To deal with this, most comparisons and difference computations
   among INTERNAL_SIZE_Ts should cast them to unsigned long, being
   aware of the fact that casting an unsigned int to a wider long does
   not sign-extend. (This also makes checking for negative numbers
   awkward.) Some of these casts result in harmless compiler warnings
   on some systems.  */
#ifndef INTERNAL_SIZE_T
# define INTERNAL_SIZE_T size_t
#endif

/* The corresponding word size.  */
#define SIZE_SZ (sizeof (INTERNAL_SIZE_T))

/* The corresponding bit mask value.  */
#define MALLOC_ALIGN_MASK (MALLOC_ALIGNMENT - 1)

/* MALLOC_ALIGNMENT is the minimum alignment for malloc'ed chunks.  It
   must be a power of two at least 2 * SIZE_SZ, even on machines for
   which smaller alignments would suffice. It may be defined as larger
   than this though. Note however that code and data structures are
   optimized for the case of 8-byte alignment.  */
#define MALLOC_ALIGNMENT (2 * SIZE_SZ < __alignof__ (long double) \
			  ? __alignof__ (long double) : 2 * SIZE_SZ)
```

> 一般に、`size_t` は `unsigned long` として定義されます。これは64ビットでは64ビットの符号なし整数、32ビットでは32ビットの符号なし整数です。

それでは `chunk` 構造体を見ていきましょう。各フィールドの具体的な説明は次のとおりです。

-   **prev_size**。この `chunk` の**物理的に隣接する前のアドレスの chunk(2つのポインタのアドレスの差が、前の chunk のサイズになる)**が空き(free)であれば、このフィールドには前の `chunk` のサイズ(`chunk` ヘッダを含む)が記録されます。そうでなければ、このフィールドは物理的に隣接する前の chunk のデータを格納するために使えます。**ここでいう前の `chunk` とは、より低いアドレスにある `chunk` を指します**。
-   **size**。この `chunk` のサイズで、`MALLOC_ALIGNMENT` の整数倍でなければなりません。要求されたメモリサイズが `MALLOC_ALIGNMENT` の整数倍でない場合は、そのサイズを満たす最小の `MALLOC_ALIGNMENT` の倍数に変換されます。これは `request2size()` マクロで行われます。32ビットシステムでは `MALLOC_ALIGNMENT` は `4` または `8` になりえ、64ビットシステムでは `MALLOC_ALIGNMENT` は `8` です。このフィールドの下位3ビットは `chunk` のサイズに影響せず、上位から順に次を表します。
    -   NON_MAIN_ARENA。現在の `chunk` がメインスレッドに属さないかどうかを記録します。1 は属さない、0 は属することを表します。
    -   IS_MAPPED。現在の `chunk` が mmap で確保されたかどうかを記録します。
    -   PREV_INUSE。前の `chunk` ブロックが確保されているかどうかを記録します。一般に、ヒープで最初に確保されるメモリブロックの size フィールドの P ビットは 1 に設定されます。これは、それより前の不正なメモリへのアクセスを防ぐためです。ある `chunk` の size の P ビットが 0 のとき、`prev_size` フィールドから1つ前の `chunk` のサイズとアドレスを取得できます。これは、空き `chunk` どうしの統合も容易にします。
-   **fd、bk**。`chunk` が確保状態のとき、fd フィールドの位置からがユーザーのデータになります。`chunk` が空きのときは、対応する空き管理リストに追加され、これらのフィールドの意味は次のようになります。
    -   fd は、次の(物理的な隣接とは限らない)空き `chunk` を指します。
    -   bk は、前の(物理的な隣接とは限らない)空き `chunk` を指します。
    -   fd と bk によって、空き `chunk` ブロックを空き `chunk` ブロックのリストに加え、一括して管理できます。
-   **fd_nextsize、bk_nextsize**。これらも `chunk` が空きのときにだけ使われますが、より大きな chunk(large chunk)に使われます。
    -   fd_nextsize は、現在の `chunk` とサイズが異なる最初の前の空きブロックを指します。bin のヘッドポインタは含みません。
    -   bk_nextsize は、現在の `chunk` とサイズが異なる最初の後ろの空きブロックを指します。bin のヘッドポインタは含みません。
    -   一般に、空きの large `chunk` は fd をたどる順序で、大きいものから小さいものへ並びます。**こうすると、適切な chunk を探すときに1つずつたどらずに済みます。**

> glibc 2.26 以降、32ビットの glibc では、`MALLOC_ALIGNMENT` マクロの定義はコンパイル時に `sysdeps/i386/malloc-alignment.h` の定義が優先的に選ばれ、その値は次の定数として定義されます。
> 
> ```c
> #define MALLOC_ALIGNMENT 16
> ```
> 
> したがって、2.26 以降の32ビット glibc では、`MALLOC_ALIGNMENT` は `SIZE_SZ` から計算される `8` ではなく、64ビット glibc と同じ値の `16` になります。

確保済みの `chunk` の姿は次のとおりです。**最初の2つのフィールドを `chunk` header、その後ろの部分を user data と呼びます。malloc で確保して得られるメモリのポインタは、実際には user data の先頭を指しています。**

`chunk` が使用状態にあるとき、その次の `chunk` の prev_size フィールドは無効なので、次の `chunk` のこの部分も現在の chunk が使えます。**これが chunk における領域の再利用です。**

```c++
chunk-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |             Size of previous chunk, if unallocated (P clear)  |
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |             Size of chunk, in bytes                     |A|M|P|
  mem-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |             User data starts here...                          .
        .                                                               .
        .             (malloc_usable_size() bytes)                      .
next    .                                                               |
chunk-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |             (size of chunk, but used for application data)    |
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |             Size of next chunk, in bytes                |A|0|1|
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

解放された `chunk` はリストに記録されます(循環双方向リストの場合も、単方向リストの場合もあります)。具体的な構造は次のとおりです。

```c++
chunk-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |             Size of previous chunk, if unallocated (P clear)  |
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
`head:' |             Size of chunk, in bytes                     |A|0|P|
  mem-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |             Forward pointer to next `chunk` in list             |
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |             Back pointer to previous `chunk` in list            |
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |             Unused space (may be 0 bytes long)                .
        .                                                               .
 next   .                                                               |
chunk-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
`foot:' |             Size of chunk, in bytes                           |
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |             Size of next chunk, in bytes                |A|0|0|
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

`chunk` が free 状態のとき、対応するサイズを記録する場所が2か所あることが分かります。

1. 自身の size フィールドに記録される。

2. その後ろの `chunk` に記録される。

**一般的な場合**、物理的に隣接する2つの空き `chunk` は統合されて1つの `chunk` になります。ヒープマネージャは prev_size フィールドと size フィールドを使って、物理的に隣接する2つの空き `chunk` ブロックを統合します。

**!!!ヒープに関するいくつかの制約については、後ほど詳しく検討します!!!**

```c++
/*
    The three exceptions to all this are:
     1. The special chunk `top' doesn't bother using the
    trailing size field since there is no next contiguous chunk
    that would have to index off it. After initialization, `top'
    is forced to always exist.  If it would become less than
    MINSIZE bytes long, it is replenished.
     2. Chunks allocated via mmap, which have the second-lowest-order
    bit M (IS_MMAPPED) set in their size fields.  Because they are
    allocated one-by-one, each must contain its own trailing size
    field.  If the M bit is set, the other bits are ignored
    (because mmapped chunks are neither in an arena, nor adjacent
    to a freed chunk).  The M bit is also used for chunks which
    originally came from a dumped heap via malloc_set_state in
    hooks.c.
     3. Chunks in fastbins are treated as allocated chunks from the
    point of view of the chunk allocator.  They are consolidated
    with their neighbors only in bulk, in malloc_consolidate.
*/
```

#### chunk 関連のマクロ

ここでは主に、`chunk` のサイズ、アライメントの検査、およびいくつかの変換のマクロを紹介します。

**chunk と mem ポインタ先頭の変換**

mem は、ユーザーが得たメモリの開始位置を指します。

```c++
/* conversion from malloc headers to user pointers, and back */
#define chunk2mem(p) ((void *) ((char *) (p) + 2 * SIZE_SZ))
#define mem2chunk(mem) ((mchunkptr)((char *) (mem) -2 * SIZE_SZ))
```

**最小の `chunk` サイズ**

```c++
/* The smallest possible chunk */
#define MIN_CHUNK_SIZE (offsetof(struct malloc_chunk, fd_nextsize))
```

ここで offsetof 関数は fd_nextsize の malloc_chunk 内でのオフセットを計算します。これは、最小の `chunk` が少なくとも bk ポインタまでを含む必要があることを示しています。

**確保できるヒープメモリの最小サイズ**

ユーザーが要求できる最小のメモリサイズは、2 * SIZE_SZ の最小の整数倍でなければなりません。

**注:現状では MIN_CHUNK_SIZE と MINSIZE のサイズは一致しています。個人的には、2つのマクロを追加した理由は、将来 malloc_chunk を変更するときに都合がよいようにするためだと思います。**

```c++
/* The smallest size we can malloc is an aligned minimal chunk */
//MALLOC_ALIGN_MASK = 2 * SIZE_SZ -1
#define MINSIZE                                                                \
    (unsigned long) (((MIN_CHUNK_SIZE + MALLOC_ALIGN_MASK) &                   \
                      ~MALLOC_ALIGN_MASK))
```

**ユーザーに割り当てるメモリがアライメントされているかの検査**

2 * SIZE_SZ のサイズでアライメントします。

```c++
/* Check if m has acceptable alignment */
// MALLOC_ALIGN_MASK = 2 * SIZE_SZ -1
#define aligned_OK(m) (((unsigned long) (m) & MALLOC_ALIGN_MASK) == 0)

#define misaligned_chunk(p)                                                    \
    ((uintptr_t)(MALLOC_ALIGNMENT == 2 * SIZE_SZ ? (p) : chunk2mem(p)) &       \
     MALLOC_ALIGN_MASK)
```

**要求バイト数の判定**

```c++
/*
   Check if a request is so large that it would wrap around zero when
   padded and aligned. To simplify some other code, the bound is made
   low enough so that adding MINSIZE will also not wrap around zero.
 */

#define REQUEST_OUT_OF_RANGE(req)                                              \
    ((unsigned long) (req) >= (unsigned long) (INTERNAL_SIZE_T)(-2 * MINSIZE))
```

**ユーザーが要求したメモリサイズを、実際に割り当てるメモリサイズに変換**

```c++
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

`chunk` が確保済み状態のとき、物理的に隣接する次の `chunk` の prev_size フィールドは必ず無効なので、このフィールドを現在の `chunk` が使えます。これが ptmalloc における `chunk` 間の再利用です。具体的な流れは次のとおりです。

1. まず、REQUEST_OUT_OF_RANGE を使って、ユーザーが要求したバイト数の chunk を割り当てられるかを判定する。
2. 次に、注意すべき点として、ユーザーが要求したバイト数はデータを格納するためのもの、つまり `chunk` header より後ろの部分です。同時に、chunk 間の再利用があるため、次の `chunk` の prev_size フィールドを使えます。したがって、ここでは SIZE_SZ だけ加えれば、内容を完全に格納できます。
3. システムで許される `chunk` の最小サイズは MINSIZE なので、それと比較する。最低要件を満たさなければ、直接 MINSIZE バイトを割り当てる。
4. それより大きければ、システムで要求する `chunk` は 2 * SIZE_SZ にアライメントされる必要があるため、アライメントのために MALLOC_ALIGN_MASK を加える。

**フラグビット関連**

```c++
/* size field is or'ed with PREV_INUSE when previous adjacent chunk in use */
#define PREV_INUSE 0x1

/* extract inuse bit of previous chunk */
#define prev_inuse(p) ((p)->mchunk_size & PREV_INUSE)

/* size field is or'ed with IS_MMAPPED if the chunk was obtained with mmap() */
#define IS_MMAPPED 0x2

/* check for mmap()'ed chunk */
#define chunk_is_mmapped(p) ((p)->mchunk_size & IS_MMAPPED)

/* size field is or'ed with NON_MAIN_ARENA if the chunk was obtained
   from a non-main arena.  This is only set immediately before handing
   the chunk to the user, if necessary.  */
#define NON_MAIN_ARENA 0x4

/* Check for chunk from main arena.  */
#define chunk_main_arena(p) (((p)->mchunk_size & NON_MAIN_ARENA) == 0)

/* Mark a chunk as not being on the main arena.  */
#define set_non_main_arena(p) ((p)->mchunk_size |= NON_MAIN_ARENA)

/*
   Bits to mask off when extracting size
   Note: IS_MMAPPED is intentionally not masked off from size field in
   macros for which mmapped chunks should never be seen. This should
   cause helpful core dumps to occur if it is tried by accident by
   people extending or adapting this malloc.
 */
#define SIZE_BITS (PREV_INUSE | IS_MMAPPED | NON_MAIN_ARENA)
```

**chunk size の取得**

```c++
/* Get size, ignoring use bits */
#define chunksize(p) (chunksize_nomask(p) & ~(SIZE_BITS))

/* Like chunksize, but do not mask SIZE_BITS.  */
#define chunksize_nomask(p) ((p)->mchunk_size)
```

**物理的に隣接する次の chunk の取得**

```c++
/* Ptr to next physical malloc_chunk. */
#define next_chunk(p) ((mchunkptr)(((char *) (p)) + chunksize(p)))
```

**前の chunk の情報の取得**

```c++
/* Size of the chunk below P.  Only valid if !prev_inuse (P).  */
#define prev_size(p) ((p)->mchunk_prev_size)

/* Set the size of the chunk below P.  Only valid if !prev_inuse (P).  */
#define set_prev_size(p, sz) ((p)->mchunk_prev_size = (sz))

/* Ptr to previous physical malloc_chunk.  Only valid if !prev_inuse (P).  */
#define prev_chunk(p) ((mchunkptr)(((char *) (p)) - prev_size(p)))
```

**現在の chunk の使用状態に関する操作**

```c++
/* extract p's inuse bit */
#define inuse(p)                                                               \
    ((((mchunkptr)(((char *) (p)) + chunksize(p)))->mchunk_size) & PREV_INUSE)

/* set/clear chunk as being inuse without otherwise disturbing */
#define set_inuse(p)                                                           \
    ((mchunkptr)(((char *) (p)) + chunksize(p)))->mchunk_size |= PREV_INUSE

#define clear_inuse(p)                                                         \
    ((mchunkptr)(((char *) (p)) + chunksize(p)))->mchunk_size &= ~(PREV_INUSE)
```

**chunk の size フィールドの設定**

```c++
/* Set size at head, without disturbing its use bit */
// SIZE_BITS = 7
#define set_head_size(p, s)                                                    \
    ((p)->mchunk_size = (((p)->mchunk_size & SIZE_BITS) | (s)))

/* Set size/use field */
#define set_head(p, s) ((p)->mchunk_size = (s))

/* Set size at footer (only when chunk is not in use) */
#define set_foot(p, s)                                                         \
    (((mchunkptr)((char *) (p) + (s)))->mchunk_prev_size = (s))
```

**指定オフセットの chunk の取得**

```c++
/* Treat space at ptr + offset as a chunk */
#define chunk_at_offset(p, s) ((mchunkptr)(((char *) (p)) + (s)))
```

**指定オフセットにある chunk の使用状態に関する操作**

```c++
/* check/set/clear inuse bits in known places */
#define inuse_bit_at_offset(p, s)                                              \
    (((mchunkptr)(((char *) (p)) + (s)))->mchunk_size & PREV_INUSE)

#define set_inuse_bit_at_offset(p, s)                                          \
    (((mchunkptr)(((char *) (p)) + (s)))->mchunk_size |= PREV_INUSE)

#define clear_inuse_bit_at_offset(p, s)                                        \
    (((mchunkptr)(((char *) (p)) + (s)))->mchunk_size &= ~(PREV_INUSE))
```

### bin

#### 概要

前に述べたとおり、ユーザーが解放した `chunk` はすぐにはシステムに返却されず、ptmalloc は heap と mmap のマッピング領域にある空きの chunk を一括して管理します。ユーザーが再びメモリの割り当てを要求したとき、ptmalloc アロケータは空きの chunk の中から適切なものを選んでユーザーに渡そうとします。これにより、頻繁なシステムコールを避け、メモリ割り当てのオーバーヘッドを減らせます。

具体的な実装では、ptmalloc は bin(箱)方式で空きの `chunk` を管理します。まず、空きの `chunk` のサイズと使用状態に基づいて、`chunk` を大きく4種類に分けます。fast bins、small bins、large bins、unsorted bin です。各種類の中にはさらに細かい区分があり、似たサイズの `chunk` は双方向リストでつながれます。つまり、各種類の bin の内部には、サイズごとに chunk を保持する、互いに無関係な複数のリストがあります。

small bins、large bins、unsorted bin について、ptmalloc はこれらを同じ1つの配列で維持しています。これらの bin に対応するデータ構造は malloc_state 内にあり、次のとおりです。

```c++
#define NBINS 128
/* Normal bins packed as described above */
mchunkptr bins[ NBINS * 2 - 2 ];
```

`bins` は主に、さまざまな bin の fd と bk を引くために使われます。

二重リンクリストでの使用を簡単にするため、各 bin の header は malloc_chunk 型に設定されています。これにより、header の型と、その特別な処理を避けられます。ただし、領域の節約と局所性の向上のため、bin の fd/bk ポインタだけを確保し、その後 repositioning tricks を使ってこれらのポインタを `malloc_chunk*` のフィールドとして扱います。


32ビットシステムを例に、bins の最初の4項目の意味は次のとおりです。

| 意味    | bin1 の fd/bin2 の prev_size | bin1 の bk/bin2 の size | bin2 の fd/bin3 の prev_size | bin2 の bk/bin3 の size |
| ----- | ---------------------- | ----------------- | ---------------------- | ----------------- |
| bin の添字 | 0                      | 1                 | 2                      | 3                 |

bin2 の prev_size、size は bin1 の fd、bk と重なっていることが分かります。リストを引くのには fd と bk しか使わないので、この重なった部分のデータは、実は bin1 の fd、bk を記録しています。つまり、後ろの bin と前の bin は一部のデータを共用していますが、記録しているのはやはり前の bin のリストのデータです。このような再利用により、領域を節約できます。

配列の中の bin は順に次のとおりです。

1. 1番目は unsorted bin で、名前のとおり、この中の `chunk` はソートされておらず、格納されている `chunk` はかなり雑多です。
2. 添字 2 から 63 までの bin を small bin と呼びます。同じ small bin のリスト内の `chunk` のサイズは同じです。隣り合う添字の small bin のリストにある `chunk` のサイズの差は**マシンワード2個分**、つまり32ビットでは8バイト、64ビットでは16バイトです。
3. small bins の後ろの bin を large bins と呼びます。large bins の各 bin には、ある範囲内の chunk が含まれ、その中の chunk は fd ポインタの順に大きいものから小さいものへ並びます。同じサイズの chunk も、同様に最近使用された順に並びます。

さらに、上記の各 bin の配置は、1つの原則に従います。**物理的に隣接する任意の2つの空き chunk が、並んで存在してはならない**。

注意すべき点として、すべての `chunk` が解放後すぐに bin に入れられるわけではありません。ptmalloc は割り当ての速度を上げるため、小さな `chunk` を**先に** fast bins のコンテナに入れます。**しかも、fastbin のコンテナ内の `chunk` の使用中フラグは常にセットされているため、上の原則を満たしません。**

bin に共通のマクロは次のとおりです。

```c++
typedef struct malloc_chunk *mbinptr;

/* addressing -- note that bin_at(0) does not exist */
#define bin_at(m, i)                                                           \
    (mbinptr)(((char *) &((m)->bins[ ((i) -1) * 2 ])) -                        \
              offsetof(struct malloc_chunk, fd))

/* analog of ++bin */
//次の bin のアドレスを取得
#define next_bin(b) ((mbinptr)((char *) (b) + (sizeof(mchunkptr) << 1)))

/* Reminders about list directionality within bins */
// この2つのマクロは bin をたどるのに使える
// bin のリスト先頭にある chunk を取得
#define first(b) ((b)->fd)
// bin のリスト末尾にある chunk を取得
#define last(b) ((b)->bk)
```

#### Fast Bin

多くのプログラムは、比較的小さなメモリブロックの確保と解放を頻繁に行います。小さな `chunk` を解放した後、隣接する空き `chunk` があるのを見つけて統合してしまうと、次に同じサイズの `chunk` を要求したときに、`chunk` を分割しなければならなくなり、ヒープの利用効率が大きく下がります。**時間の大半を、統合、分割、そしてその間の検査に費やしてしまうからです。**そのため ptmalloc では fast bin を特別に設計しており、対応する変数は malloc state の fastbinsY です。

```c++
/*
   Fastbins

    An array of lists holding recently freed small chunks.  Fastbins
    are not doubly linked.  It is faster to single-link them, and
    since chunks are never removed from the middles of these lists,
    double linking is not necessary. Also, unlike regular bins, they
    are not even processed in FIFO order (they use faster LIFO) since
    ordering doesn't much matter in the transient contexts in which
    fastbins are normally used.

    Chunks in fastbins keep their inuse bit set, so they cannot
    be consolidated with other free chunks. malloc_consolidate
    releases all chunks in fastbins and consolidates them with
    other free chunks.
 */
typedef struct malloc_chunk *mfastbinptr;

/*
    This is in malloc_state.
    /* Fastbins */
    mfastbinptr fastbinsY[ NFASTBINS ];
*/
```

fast bin をより効率よく使うため、glibc は単方向リストでその中の各 bin を構成し、**各 bin は LIFO 方式をとります**。最近解放された `chunk` ほど早く割り当てられるため、局所性によりよく適合します。つまり、ユーザーが必要とする `chunk` のサイズが fastbin の最大サイズ以下のとき、ptmalloc はまず fastbin の対応する bin に該当サイズの空きブロックがあるかを調べ、あれば、そのまま bin から chunk を取得します。なければ、ptmalloc は続く一連の操作を行います。

デフォルトでは(**32ビットシステムを例に**)、fastbin がデフォルトでサポートする最大の `chunk` のデータ領域サイズは 64 バイトです。ただし、サポートできる chunk のデータ領域の最大は 80 バイトです。そのほか、fastbin がサポートできる bin の数は最大 10 個で、データ領域が 8 バイトのものから 80 バイトまでです(ここで言っているのはデータ領域のサイズ、つまり prev_size と size のフィールド部分を除いたサイズです)。定義は次のとおりです。

```c++
#define NFASTBINS (fastbin_index(request2size(MAX_FAST_SIZE)) + 1)

#ifndef DEFAULT_MXFAST
#define DEFAULT_MXFAST (64 * SIZE_SZ / 4)
#endif
  
/* The maximum fastbin request size we support */
#define MAX_FAST_SIZE (80 * SIZE_SZ / 4)

/*
   Since the lowest 2 bits in max_fast don't matter in size comparisons,
   they are used as flags.
 */

/*
   FASTCHUNKS_BIT held in max_fast indicates that there are probably
   some fastbin chunks. It is set true on entering a chunk into any
   fastbin, and cleared only in malloc_consolidate.

   The truth value is inverted so that have_fastchunks will be true
   upon startup (since statics are zero-filled), simplifying
   initialization checks.
 */
//割り当て領域に fast bin chunk があるかを判定。1 はなしを表す
#define FASTCHUNKS_BIT (1U)

#define have_fastchunks(M) (((M)->flags & FASTCHUNKS_BIT) == 0)
#define clear_fastchunks(M) catomic_or(&(M)->flags, FASTCHUNKS_BIT)
#define set_fastchunks(M) catomic_and(&(M)->flags, ~FASTCHUNKS_BIT)

/*
   NONCONTIGUOUS_BIT indicates that MORECORE does not return contiguous
   regions.  Otherwise, contiguity is exploited in merging together,
   when possible, results from consecutive MORECORE calls.

   The initial value comes from MORECORE_CONTIGUOUS, but is
   changed dynamically if mmap is ever used as an sbrk substitute.
 */
// MORECORE が連続したメモリ領域を返すかどうか。
// メイン割り当て領域の MORECORE は実は sbr() で、デフォルトでは連続した仮想アドレス空間を返す
// メイン以外の割り当て領域は mmap() で大きな仮想メモリを確保し、それを切り分けてメイン割り当て領域の動作を模倣する
// 一方、デフォルトでは mmap のマッピング領域は仮想アドレス空間の連続を保証しないため、メイン以外の割り当て領域はデフォルトで非連続な仮想アドレス空間を割り当てる。
#define NONCONTIGUOUS_BIT (2U)

#define contiguous(M) (((M)->flags & NONCONTIGUOUS_BIT) == 0)
#define noncontiguous(M) (((M)->flags & NONCONTIGUOUS_BIT) != 0)
#define set_noncontiguous(M) ((M)->flags |= NONCONTIGUOUS_BIT)
#define set_contiguous(M) ((M)->flags &= ~NONCONTIGUOUS_BIT)

/* ARENA_CORRUPTION_BIT is set if a memory corruption was detected on the
   arena.  Such an arena is no longer used to allocate chunks.  Chunks
   allocated in that arena before detecting corruption are not freed.  */

#define ARENA_CORRUPTION_BIT (4U)

#define arena_is_corrupt(A) (((A)->flags & ARENA_CORRUPTION_BIT))
#define set_arena_corrupt(A) ((A)->flags |= ARENA_CORRUPTION_BIT)

/*
   Set value of max_fast.
   Use impossibly small value if 0.
   Precondition: there are no existing fastbin chunks.
   Setting the value clears fastchunk bit but preserves noncontiguous bit.
 */

#define set_max_fast(s)                                                        \
    global_max_fast =                                                          \
        (((s) == 0) ? SMALLBIN_WIDTH : ((s + SIZE_SZ) & ~MALLOC_ALIGN_MASK))
#define get_max_fast() global_max_fast
```

ptmalloc はデフォルトで set_max_fast(s) を呼び出し、グローバル変数 global_max_fast を DEFAULT_MXFAST に設定します。これが fast bins 内の `chunk` の最大値の設定です。MAX_FAST_SIZE が 0 に設定されると、システムは fastbin をサポートしなくなります。

**fastbin の添字**

```c++

#define fastbin(ar_ptr, idx) ((ar_ptr)->fastbinsY[ idx ])

/* offset 2 to use otherwise unindexable first 2 bins */
// chunk size=2*size_sz*(2+idx)
// ここで 2 を引くのは、そうしないと最初の2つの bin を引けないため。
#define fastbin_index(sz)                                                      \
    ((((unsigned int) (sz)) >> (SIZE_SZ == 8 ? 4 : 3)) - 2)
```

**特に注意すべき点として、fastbin の範囲の `chunk` の inuse は常に 1 にセットされています。したがって、それらは解放されたほかの `chunk` と統合されません。**

ただし、解放した `chunk` と、それに隣接する空き `chunk` を統合した後のサイズが FASTBIN_CONSOLIDATION_THRESHOLD より大きいときは、メモリの断片化がかなり進んでいる可能性があるため、メモリ断片化がシステムに与える影響を減らすために、fast bins 内の chunk をすべて統合する必要があります。

```c++
/*
   FASTBIN_CONSOLIDATION_THRESHOLD is the size of a chunk in free()
   that triggers automatic consolidation of possibly-surrounding
   fastbin chunks. This is a heuristic, so the exact value should not
   matter too much. It is defined at half the default trim threshold as a
   compromise heuristic to only attempt consolidation if it is likely
   to lead to trimming. However, it is not dynamically tunable, since
   consolidation reduces fragmentation surrounding large chunks even
   if trimming is not used.
 */

#define FASTBIN_CONSOLIDATION_THRESHOLD (65536UL)
```

**malloc_consolidate 関数は、fastbin 内の、ほかの `chunk` と統合できるすべての `chunk` をまとめて統合します。具体的には、後続の関数の詳細な解析を参照してください。**

```
/*
	Chunks in fastbins keep their inuse bit set, so they cannot
    be consolidated with other free chunks. malloc_consolidate
    releases all chunks in fastbins and consolidates them with
    other free chunks.
 */
```

#### Small Bin

small bins における各 `chunk` のサイズと、その `chunk` が属する bin の index との関係は chunk_size = 2 * SIZE_SZ *index で、具体的には次のとおりです。

| 添字   | SIZE_SZ=4(32ビット) | SIZE_SZ=8(64ビット) |
| ---- | -------------- | -------------- |
| 2    | 16             | 32             |
| 3    | 24             | 48             |
| 4    | 32             | 64             |
| 5    | 40             | 80             |
| x    | 2\*4\*x        | 2\*8\*x        |
| 63   | 504            | 1008           |

small bins には全部で 62 個の循環双方向リストがあり、各リストに格納される `chunk` のサイズはすべて同じです。たとえば32ビットシステムでは、添字 2 に対応する双方向リストに格納される `chunk` のサイズはどれも 16 バイトです。各リストにはリストの先頭ノードがあり、これによりリスト内部のノードの管理が容易になります。さらに、**small bins の各 bin に対応するリストは FIFO の規則を採用しています**。そのため、同じリストの中で先に解放された `chunk` が先に割り当てられます。

small bin 関連のマクロは次のとおりです。

```c++
#define NSMALLBINS 64
#define SMALLBIN_WIDTH MALLOC_ALIGNMENT
// small bin の添字を補正する必要があるか
#define SMALLBIN_CORRECTION (MALLOC_ALIGNMENT > 2 * SIZE_SZ)

#define MIN_LARGE_SIZE ((NSMALLBINS - SMALLBIN_CORRECTION) * SMALLBIN_WIDTH)
//chunk のサイズが small bin の範囲内か判定
#define in_smallbin_range(sz)                                                  \
    ((unsigned long) (sz) < (unsigned long) MIN_LARGE_SIZE)
// chunk のサイズから、対応する small bin の添字を得る。
#define smallbin_index(sz)                                                     \
    ((SMALLBIN_WIDTH == 16 ? (((unsigned) (sz)) >> 4)                          \
                           : (((unsigned) (sz)) >> 3)) +                       \
     SMALLBIN_CORRECTION)
```

**もしかすると、疑問に思う人もいるでしょう。fastbin と small bin の `chunk` のサイズはかなりの部分が重なっているのだから、small bin の該当サイズの bin は役に立たないのではないか、と。** 実はそうではありません。fast bin の `chunk` は small bin に入れられることがあり、これは後で具体的なソースコードを解析するときに深く実感できるでしょう。

#### Large Bin

large bins には全部で 63 個の bin があり、各 bin 内の `chunk` のサイズは一様ではなく、ある範囲内にあります。さらに、この 63 個の bin は 6 つのグループに分けられ、各グループの bin 内の `chunk` のサイズの公差は同じです。具体的には次のとおりです。

| グループ    | 個数   | 公差      |
| ---- | ---- | ------- |
| 1    | 32   | 64B     |
| 2    | 16   | 512B    |
| 3    | 8    | 4096B   |
| 4    | 4    | 32768B  |
| 5    | 2    | 262144B |
| 6    | 1    | 制限なし     |

ここでは32ビットプラットフォームの large bin を例にします。最初の large bin の先頭の `chunk` サイズは 512 バイトで、第1グループにあるため、この bin に格納できる `chunk` のサイズ範囲は [512,512+64) です。

large bin に関するマクロは次のとおりです。ここでは32ビットプラットフォームで、最初の large bin の先頭の `chunk` サイズが 512 バイトの場合を例にします。512>>6 = 8 なので、その添字は 56+8=64 です。

```c++
#define largebin_index_32(sz)                                                  \
    (((((unsigned long) (sz)) >> 6) <= 38)                                     \
         ? 56 + (((unsigned long) (sz)) >> 6)                                  \
         : ((((unsigned long) (sz)) >> 9) <= 20)                               \
               ? 91 + (((unsigned long) (sz)) >> 9)                            \
               : ((((unsigned long) (sz)) >> 12) <= 10)                        \
                     ? 110 + (((unsigned long) (sz)) >> 12)                    \
                     : ((((unsigned long) (sz)) >> 15) <= 4)                   \
                           ? 119 + (((unsigned long) (sz)) >> 15)              \
                           : ((((unsigned long) (sz)) >> 18) <= 2)             \
                                 ? 124 + (((unsigned long) (sz)) >> 18)        \
                                 : 126)

#define largebin_index_32_big(sz)                                              \
    (((((unsigned long) (sz)) >> 6) <= 45)                                     \
         ? 49 + (((unsigned long) (sz)) >> 6)                                  \
         : ((((unsigned long) (sz)) >> 9) <= 20)                               \
               ? 91 + (((unsigned long) (sz)) >> 9)                            \
               : ((((unsigned long) (sz)) >> 12) <= 10)                        \
                     ? 110 + (((unsigned long) (sz)) >> 12)                    \
                     : ((((unsigned long) (sz)) >> 15) <= 4)                   \
                           ? 119 + (((unsigned long) (sz)) >> 15)              \
                           : ((((unsigned long) (sz)) >> 18) <= 2)             \
                                 ? 124 + (((unsigned long) (sz)) >> 18)        \
                                 : 126)

// XXX It remains to be seen whether it is good to keep the widths of
// XXX the buckets the same or whether it should be scaled by a factor
// XXX of two as well.
#define largebin_index_64(sz)                                                  \
    (((((unsigned long) (sz)) >> 6) <= 48)                                     \
         ? 48 + (((unsigned long) (sz)) >> 6)                                  \
         : ((((unsigned long) (sz)) >> 9) <= 20)                               \
               ? 91 + (((unsigned long) (sz)) >> 9)                            \
               : ((((unsigned long) (sz)) >> 12) <= 10)                        \
                     ? 110 + (((unsigned long) (sz)) >> 12)                    \
                     : ((((unsigned long) (sz)) >> 15) <= 4)                   \
                           ? 119 + (((unsigned long) (sz)) >> 15)              \
                           : ((((unsigned long) (sz)) >> 18) <= 2)             \
                                 ? 124 + (((unsigned long) (sz)) >> 18)        \
                                 : 126)

#define largebin_index(sz)                                                     \
    (SIZE_SZ == 8 ? largebin_index_64(sz) : MALLOC_ALIGNMENT == 16             \
                                                ? largebin_index_32_big(sz)    \
                                                : largebin_index_32(sz))
```

#### Unsorted Bin

unsorted bin は、空き `chunk` が所属する bin に戻る前のバッファとみなせます。

glibc での具体的な説明は次のとおりです。

```c++
/*
   Unsorted chunks

    All remainders from chunk splits, as well as all returned chunks,
    are first placed in the "unsorted" bin. They are then placed
    in regular bins after malloc gives them ONE chance to be used before
    binning. So, basically, the unsorted_chunks list acts as a queue,
    with chunks being placed on it in free (and malloc_consolidate),
    and taken off (to be either used or placed in bins) in malloc.

    The NON_MAIN_ARENA flag is never set for unsorted chunks, so it
    does not have to be taken into account in size comparisons.
 */
```

次のマクロから分かります。

```c++
/* The otherwise unindexable 1-bin is used to hold unsorted chunks. */
#define unsorted_chunks(M) (bin_at(M, 1))
```

unsorted bin は、先に述べた bin 配列の添字 1 の位置にあります。したがって unsorted bin のリストは1つだけです。unsorted bin 内の空き `chunk` は順序が乱れた状態で、主に2つの由来があります。

- 比較的大きな `chunk` が2つに分割されたとき、残りの部分が MINSIZE より大きければ、unsorted bin に入れられる。
- fast bin に属さない chunk を解放し、その `chunk` が top `chunk` と隣接していないとき、その `chunk` はまず unsorted bin に入れられる。top `chunk` の説明については、下の紹介を参照してください。

さらに、Unsorted Bin は使用の過程で、FIFO の順でたどります。

#### common macro

ここでは、いくつかの共通のマクロを紹介します。

**chunk のサイズから、chunk が属する添字を統一的に得る**

```c++
#define bin_index(sz)                                                          \
    ((in_smallbin_range(sz)) ? smallbin_index(sz) : largebin_index(sz))
```

### Top Chunk

glibc での top `chunk` の説明は次のとおりです。

```c++
/*
   Top

    The top-most available chunk (i.e., the one bordering the end of
    available memory) is treated specially. It is never included in
    any bin, is used only if no other chunk is available, and is
    released back to the system if it is very large (see
    M_TRIM_THRESHOLD).  Because top initially
    points to its own bin with initial zero size, thus forcing
    extension on the first malloc request, we avoid having any special
    code in malloc to check whether it even exists yet. But we still
    need to do so when getting memory from system, so we make
    initial_top treat the bin as a legal but unusable chunk during the
    interval between initialization and the first call to
    sysmalloc. (This is somewhat delicate, since it relies on
    the 2 preceding words to be zero during this interval as well.)
 */

/* Conveniently, the unsorted bin can be used as dummy top on first call */
#define initial_top(M) (unsorted_chunks(M))
```

プログラムが最初に malloc を行うとき、heap は2つのブロックに分けられ、1つはユーザーに渡され、残りが top chunk になります。実は、top `chunk` とは、現在のヒープの物理アドレスで最も高い位置にある chunk のことです。この `chunk` はどの bin にも属さず、その役割は、すべての bin がユーザーの要求サイズを満たせないとき、そのサイズが指定のサイズ以上であれば割り当て、残りの部分を新しい top chunk とすることです。そうでなければ、heap を拡張してから割り当てます。main arena では sbrk で heap を拡張し、thread arena では mmap で新しい heap を割り当てます。

注意すべき点として、top `chunk` の prev_inuse ビットは常に 1 です。そうでないと、その前の chunk が top chunk に統合されてしまいます。

**初期状態では、unsorted `chunk` を top chunk として扱えます。**

### last remainder

ユーザーが malloc でメモリの割り当てを要求したとき、ptmalloc2 が見つけた `chunk` が要求したメモリサイズと一致しないことがあります。その場合、分割した後の残りの部分を last remainder `chunk` と呼び、unsort bin にもこのブロックが格納されます。top `chunk` を分割した残りの部分は last remainder にはなりません。

## マクロ構造

### arena

これまでに紹介した例では、メインスレッドでも新しく作られたスレッドでも、最初にメモリを要求するときには独立した arena が用意されていました。では、すべてのスレッドに独立した arena があるのでしょうか。以下で具体的に紹介します。

#### arena の数

システムによって、arena の数の[制約](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/arena.c#L847)は次のとおりです。

```text
For 32 bit systems:
     Number of arena = 2 * number of cores.
For 64 bit systems:
     Number of arena = 8 * number of cores.
```

明らかに、すべてのスレッドに対応する arena があるわけではありません。64ビットシステムでなぜそのように設定されているのかは、私にも分かりませんでした。また、システムのコア数には限りがあるため、スレッド数がコア数の2倍(ハイパースレッディング)を超えると、必ず待ち状態になるスレッドが出ます。したがって、スレッドごとに arena を割り当てる必要はありません。

#### arena の割り当て規則

**追記予定です。**

#### 違い

thread とは異なり、main_arena は確保した heap の中にはなく、グローバル変数で、libc.so のデータセグメントにあります。

### heap_info

プログラムの実行開始時、各スレッドには heap 領域がありません。メモリを要求するときに、対応する情報を記録する構造が必要になり、heap_info の役割がそれです。さらに、その heap のリソースを使い切ったら、再びメモリを要求しなければなりません。また、一般に確保された heap は連続していないため、異なる heap 間のつながりを記録する構造が必要です。

**このデータ構造は、Memory Mapping Segment から確保されるメモリ、つまりメインスレッド以外のスレッドのために用意されたものです。**

メインスレッドは sbrk() 関数で program break location を拡張することで得られます(Memory Mapping Segment に達するまで)。heap は1つだけで、heap_info データ構造はありません。

heap_info の主な構造は次のとおりです。

```c++
#define HEAP_MIN_SIZE (32 * 1024)
#ifndef HEAP_MAX_SIZE
# ifdef DEFAULT_MMAP_THRESHOLD_MAX
#  define HEAP_MAX_SIZE (2 * DEFAULT_MMAP_THRESHOLD_MAX)
# else
#  define HEAP_MAX_SIZE (1024 * 1024) /* must be a power of two */
# endif
#endif

/* HEAP_MIN_SIZE and HEAP_MAX_SIZE limit the size of mmap()ed heaps
   that are dynamically created for multi-threaded programs.  The
   maximum size must be a power of two, for fast determination of
   which heap belongs to a chunk.  It should be much larger than the
   mmap threshold, so that requests with a size just below that
   threshold can be fulfilled without creating too many heaps.  */

/***************************************************************************/

/* A heap is a single contiguous memory region holding (coalesceable)
   malloc_chunks.  It is allocated with mmap() and always starts at an
   address aligned to HEAP_MAX_SIZE.  */

typedef struct _heap_info
{
  mstate ar_ptr; /* Arena for this heap. */
  struct _heap_info *prev; /* Previous heap. */
  size_t size;   /* Current size in bytes. */
  size_t mprotect_size; /* Size in bytes that has been mprotected
                           PROT_READ|PROT_WRITE.  */
  /* Make sure the following data is properly aligned, particularly
     that sizeof (heap_info) + 2 * SIZE_SZ is a multiple of
     MALLOC_ALIGNMENT. */
  char pad[-6 * SIZE_SZ & MALLOC_ALIGN_MASK];
} heap_info;
```

この構造は主にヒープの基本情報を記述しており、次を含みます。

- ヒープに対応する arena のアドレス
- スレッドが1つヒープを確保した後、それを使い切ることがあり、その場合は再び確保しなければなりません。したがって、1つのスレッドが複数のヒープを持つことがあります。prev は1つ前の heap_info のアドレスを記録します。ここから、各ヒープの heap_info は単方向リストでつながれていることが分かります。
- size は現在のヒープのサイズを表す
- 最後の部分はアライメントを保証する

!!! note "pad の中の負数の由来は何でしょうか?"
    `pad` は、確保される領域が `MALLOC_ALIGN_MASK+1`(`MALLOC_ALIGN_MASK_1` と記します)にアライメントされることを保証するためのものです。`pad` の前には、この構造体に `SIZE_SZ` 大のメンバが全部で 6 個あります。`MALLOC_ALIGN_MASK_1` バイトのアライメントを保証するには `pad` が必要になることがあります。構造体の最終的なサイズを `MALLOC_ALIGN_MASK_1*x`(`x` は自然数)と仮定すると、`pad` に必要な領域は `MALLOC_ALIGN_MASK_1 * x - 6 * SIZE_SZ = (MALLOC_ALIGN_MASK_1 * x - 6 * SIZE_SZ) % MALLOC_ALIGN_MASK_1 = 0 - 6 * SIZE_SZ % MALLOC_ALIGN_MASK_1=-6 * SIZE_SZ % MALLOC_ALIGN_MASK_1 = -6 * SIZE_SZ & MALLOC_ALIGN_MASK` となります。

この構造はかなり重要そうに見えますが、malloc の実装全体を丁寧に読んでみると、登場する頻度は高くないことが分かります。

### malloc_state

この構造はヒープの管理に使われ、各 arena が現在確保しているメモリの具体的な状態を記録します。たとえば、空き chunk があるか、どんなサイズの空き chunk があるか、などです。thread arena でも main arena でも、malloc state 構造は1つだけです。thread の arena は複数ありえるため、malloc state 構造は最新に確保された arena の中に置かれます。

**注意:main arena の malloc_state は heap segment の一部ではなく、グローバル変数で、libc.so のデータセグメントに格納されています。**

その構造は次のとおりです。

```c++
struct malloc_state {
    /* Serialize access.  */
    __libc_lock_define(, mutex);

    /* Flags (formerly in max_fast).  */
    int flags;

    /* Fastbins */
    mfastbinptr fastbinsY[ NFASTBINS ];

    /* Base of the topmost chunk -- not otherwise kept in a bin */
    mchunkptr top;

    /* The remainder from the most recent split of a small request */
    mchunkptr last_remainder;

    /* Normal bins packed as described above */
    mchunkptr bins[ NBINS * 2 - 2 ];

    /* Bitmap of bins, help to speed up the process of determinating if a given bin is definitely empty.*/
    unsigned int binmap[ BINMAPSIZE ];

    /* Linked list, points to the next arena */
    struct malloc_state *next;

    /* Linked list for free arenas.  Access to this field is serialized
       by free_list_lock in arena.c.  */
    struct malloc_state *next_free;

    /* Number of threads attached to this arena.  0 if the arena is on
       the free list.  Access to this field is serialized by
       free_list_lock in arena.c.  */
    INTERNAL_SIZE_T attached_threads;

    /* Memory allocated from the system in this arena.  */
    INTERNAL_SIZE_T system_mem;
    INTERNAL_SIZE_T max_system_mem;
};
```

-   __libc_lock_define(, mutex);
    -   この変数は、プログラムが同じ割り当て領域へ直列にアクセスするように制御するために使います。あるスレッドが割り当て領域を取得すると、ほかのスレッドがその割り当て領域にアクセスするには、そのスレッドの割り当てが完了するまで待たなければなりません。

-   flags
    -   flags は割り当て領域のいくつかのフラグを記録します。たとえば bit0 は割り当て領域に `fast bin chunk` があるかどうかを記録し、bit1 は割り当て領域が連続した仮想アドレス空間を返せるかどうかを示します。具体的には次のとおりです。

```c

/*
   FASTCHUNKS_BIT held in max_fast indicates that there are probably
   some fastbin chunks. It is set true on entering a chunk into any
   fastbin, and cleared only in malloc_consolidate.
   The truth value is inverted so that have_fastchunks will be true
   upon startup (since statics are zero-filled), simplifying
   initialization checks.
 */

#define FASTCHUNKS_BIT (1U)

#define have_fastchunks(M) (((M)->flags & FASTCHUNKS_BIT) == 0)
#define clear_fastchunks(M) catomic_or(&(M)->flags, FASTCHUNKS_BIT)
#define set_fastchunks(M) catomic_and(&(M)->flags, ~FASTCHUNKS_BIT)

/*
   NONCONTIGUOUS_BIT indicates that MORECORE does not return contiguous
   regions.  Otherwise, contiguity is exploited in merging together,
   when possible, results from consecutive MORECORE calls.
   The initial value comes from MORECORE_CONTIGUOUS, but is
   changed dynamically if mmap is ever used as an sbrk substitute.
 */

#define NONCONTIGUOUS_BIT (2U)

#define contiguous(M) (((M)->flags & NONCONTIGUOUS_BIT) == 0)
#define noncontiguous(M) (((M)->flags & NONCONTIGUOUS_BIT) != 0)
#define set_noncontiguous(M) ((M)->flags |= NONCONTIGUOUS_BIT)
#define set_contiguous(M) ((M)->flags &= ~NONCONTIGUOUS_BIT)

/* ARENA_CORRUPTION_BIT is set if a memory corruption was detected on the
   arena.  Such an arena is no longer used to allocate chunks.  Chunks
   allocated in that arena before detecting corruption are not freed.  */

#define ARENA_CORRUPTION_BIT (4U)

#define arena_is_corrupt(A) (((A)->flags & ARENA_CORRUPTION_BIT))
#define set_arena_corrupt(A) ((A)->flags |= ARENA_CORRUPTION_BIT)

```

-   fastbinsY[NFASTBINS]
    -   各 fast `chunk` リストの先頭へのポインタを格納する
-   top
    -   割り当て領域の top chunk を指す
-   last_reminder
    -   最新の `chunk` を分割した後に残った部分
-   bins
    -   unstored bin、small bins、large bins の `chunk` リストを格納するために使う。
-   binmap
    -   ptmalloc は、ある bin に空き `chunk` が含まれているかどうかを 1 ビットで示す。

### malloc_par

**!!追記予定です!!**
