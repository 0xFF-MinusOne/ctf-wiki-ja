# メモリブロックの確保

## __libc_malloc

一般にはメモリブロックを確保するのに malloc 関数を使いますが、glibc のソースコードの実装を詳しく見ると、実は malloc 関数は存在しません。この関数が実際に呼び出しているのは \_\_libc_malloc 関数です。なぜ直接 malloc 関数を書かないのかというと、場合によっては異なる名前が必要になることがあるからです。また、__libc_malloc 関数は _int_malloc 関数を単純にラップしているだけで、\_int_malloc こそがメモリブロック確保の中核です。以下、具体的な実装を詳しく分析します。

この関数はまず、メモリ確保関数のフック関数(__malloc_hook)があるかどうかを調べます。これは主にユーザー定義のヒープ確保関数のためのもので、ユーザーがヒープ確保関数を素早く差し替えてテストしやすくしています。ここで注意すべきは、**ユーザーが要求したバイト数は、メモリ確保関数に入ると符号なし整数になる**ことです。

```c++
// wapper for int_malloc
void *__libc_malloc(size_t bytes) {
    mstate ar_ptr;
    void * victim;
    // メモリ確保フックがあるかを調べ、あれば、フックを呼び出して返す。
    void *(*hook)(size_t, const void *) = atomic_forced_read(__malloc_hook);
    if (__builtin_expect(hook != NULL, 0))
        return (*hook)(bytes, RETURN_ADDRESS(0));

```

次に arena を探して、メモリの確保を試みます。

```c++
    arena_get(ar_ptr, bytes);
```

続いて _int_malloc 関数を呼び出して、対応するメモリを確保します。

```c++
    victim = _int_malloc(ar_ptr, bytes);
```

確保に失敗した場合、ptmalloc は利用可能な別の arena を探し直して、メモリを確保しようとします。

```c++
    /* Retry with another arena only if we were able to find a usable arena
       before.  */
    if (!victim && ar_ptr != NULL) {
        LIBC_PROBE(memory_malloc_retry, 1, bytes);
        ar_ptr = arena_get_retry(ar_ptr, bytes);
        victim = _int_malloc(ar_ptr, bytes);
    }
```

arena を確保できていた場合は、終了する前にロックを解除する必要もあります。

```c++
    if (ar_ptr != NULL) __libc_lock_unlock(ar_ptr->mutex);
```

現在の状態が次の条件を満たしているかを判断します。

- メモリを確保できていない
- mmap のメモリである
- **確保したメモリが、その確保元の arena の中になければならない**

```c++
    assert(!victim || chunk_is_mmapped(mem2chunk(victim)) ||
           ar_ptr == arena_for_chunk(mem2chunk(victim)));
```

最後にメモリを返します。

```c++
    return victim;
}
```

## _int_malloc

_int_malloc はメモリ確保の中核となる関数で、その中心的な考え方は次のとおりです。

1. ユーザーが要求した**メモリブロックのサイズ**と、**そのサイズの chunk が通常どの程度使われるか**(fastbin chunk、small chunk、large chunk)に応じて、異なる確保方法を順に実装している。
2. 小さい方から大きい方へ、異なる bin に要求を満たせる空きブロックがあるかを順に調べる。
3. すべての空き chunk で要求を満たせないとき、top chunk を考慮する。
4. top chunk でも満たせないとき、初めてヒープアロケータはメモリブロックの要求を行う。

この関数に入ると、すぐに必要な一連の変数が定義され、ユーザーが要求したメモリサイズが内部の chunk サイズに変換されます。

```c++
static void *_int_malloc(mstate av, size_t bytes) {
    INTERNAL_SIZE_T nb;  /* normalized request size */
    unsigned int    idx; /* associated bin index */
    mbinptr         bin; /* associated bin */

    mchunkptr       victim;       /* inspected/selected chunk */
    INTERNAL_SIZE_T size;         /* its size */
    int             victim_index; /* its bin index */

    mchunkptr     remainder;      /* remainder from a split */
    unsigned long remainder_size; /* its size */

    unsigned int block; /* bit map traverser */
    unsigned int bit;   /* bit map traverser */
    unsigned int map;   /* current word of binmap */

    mchunkptr fwd; /* misc temp for linking */
    mchunkptr bck; /* misc temp for linking */

    const char *errstr = NULL;

    /*
       Convert request size to internal form by adding SIZE_SZ bytes
       overhead plus possibly more to obtain necessary alignment and/or
       to obtain a size of at least MINSIZE, the smallest allocatable
       size. Also, checked_request2size traps (returning 0) request sizes
       that are so large that they wrap around zero when padded and
       aligned.
     */

    checked_request2size(bytes, nb);
```

### arena

```c++
    /* There are no usable arenas.  Fall back to sysmalloc to get a chunk from
       mmap.  */
    if (__glibc_unlikely(av == NULL)) {
        void *p = sysmalloc(nb, av);
        if (p != NULL) alloc_perturb(p, bytes);
        return p;
    }
```

### fast bin

要求された chunk のサイズが fastbin の範囲内の場合です。**ここで比較されるのは符号なし整数であることに注意してください**。**また、chunk は fastbin の先頭ノードから取り出されます**。

```c++
    /*
       If the size qualifies as a fastbin, first check corresponding bin.
       This code is safe to execute even if av is not yet initialized, so we
       can try it without checking, which saves some time on this fast path.
     */

    if ((unsigned long) (nb) <= (unsigned long) (get_max_fast())) {
        // 対応する fastbin のインデックスを得る
        idx             = fastbin_index(nb);
        // 対応する fastbin の先頭ポインタを得る
        mfastbinptr *fb = &fastbin(av, idx);
        mchunkptr    pp = *fb;
        // fd をたどって、対応する bin に空き chunk があるかを調べる。
        do {
            victim = pp;
            if (victim == NULL) break;
        } while ((pp = catomic_compare_and_exchange_val_acq(fb, victim->fd,
                                                            victim)) != victim);
        // 利用できる chunk が存在する
        if (victim != 0) {
            // 取り出した chunk のサイズが、対応する fastbin のインデックスと一致するかを検査する。
            // 取得した victim から、chunksize で そのサイズを計算する。
            // fastbin_index で chunk のインデックスを計算する。
            if (__builtin_expect(fastbin_index(chunksize(victim)) != idx, 0)) {
                errstr = "malloc(): memory corruption (fast)";
            errout:
                malloc_printerr(check_action, errstr, chunk2mem(victim), av);
                return NULL;
            }
            // 詳細な検査。DEBUG のときにしか役に立たない
            check_remalloced_chunk(av, victim, nb);
            // 取得した chunk を mem の形式に変換する
            void *p = chunk2mem(victim);
            // perturb_type が設定されていれば、取得した chunk を perturb_type ^ 0xff で初期化する
            alloc_perturb(p, bytes);
            return p;
        }
    }
```

### small bin

要求されたメモリブロックの範囲が small bin の範囲内であれば、次の流れが実行されます。

```c++
    /*
       If a small request, check regular bin.  Since these "smallbins"
       hold one size each, no searching within bins is necessary.
       (For a large request, we need to wait until unsorted chunks are
       processed to find best fit. But for small ones, fits are exact
       anyway, so we can check now, which is faster.)
     */

    if (in_smallbin_range(nb)) {
        // small bin のインデックスを取得
        idx = smallbin_index(nb);
        // 対応する small bin の chunk ポインタを取得
        bin = bin_at(av, idx);
        // まず victim = last(bin) を実行し、small bin の最後の chunk を取得
        // victim = bin なら、その bin は空である。
        // 等しくなければ、次の 2 通りの場合がある
        if ((victim = last(bin)) != bin) {
            // 1 つ目、small bin がまだ初期化されていない場合。
            if (victim == 0) /* initialization check */
                // 初期化を行い、fast bins の chunk を統合する
                malloc_consolidate(av);
            // 2 つ目、small bin に空き chunk が存在する場合
            else {
                // small bin の末尾から 2 番目の chunk を取得する。
                bck = victim->bk;
                // bck->fd が victim かどうかを検査し、偽造を防ぐ
                if (__glibc_unlikely(bck->fd != victim)) {
                    errstr = "malloc(): smallbin double linked list corrupted";
                    goto errout;
                }
                // victim に対応する inuse ビットを設定
                set_inuse_bit_at_offset(victim, nb);
                // small bin のリストを変更し、small bin の最後の chunk を取り出す
                bin->bk = bck;
                bck->fd = bin;
                // main_arena でなければ、対応するフラグを設定
                if (av != &main_arena) set_non_main_arena(victim);
                // 詳細な検査。デバッグ時以外は効果がない
                check_malloced_chunk(av, victim, nb);
                // 確保した chunk を対応する mem の状態に変換
                void *p = chunk2mem(victim);
                // perturb_type が設定されていれば、取得した chunk を perturb_type ^ 0xff で初期化する
                alloc_perturb(p, bytes);
                return p;
            }
        }
    }
```

### large bin

fast bin と small bin の chunk のどちらでもユーザーが要求した chunk サイズを満たせないときは、large bin かどうかを考えます。ただし実際には、large bin では対応する bin の chunk を直接走査するのではなく、まず malloc_consolidate(malloc_state 関連の関数を参照)関数で fast bin の chunk を処理します。統合できそうな chunk はまず統合してから unsorted bin に入れ、統合できないものはそのまま unsorted bin に入れ、そのうえで以下の大きなループの中で対応する処理を行います。**なぜ対応する bin から large chunk を直接取り出さないのでしょうか。これは ptmalloc の仕組みで、large chunk を確保する前にヒープ中の断片化した chunk を統合して、ヒープ中の断片を減らすためです。**

```c++
    /*
       If this is a large request, consolidate fastbins before continuing.
       While it might look excessive to kill all fastbins before
       even seeing if there is space available, this avoids
       fragmentation problems normally associated with fastbins.
       Also, in practice, programs tend to have runs of either small or
       large requests, but less often mixtures, so consolidation is not
       invoked all that often in most programs. And the programs that
       it is called frequently in otherwise tend to fragment.
     */

    else {
        // large bin のインデックスを取得する。
        idx = largebin_index(nb);
        // fastbin が存在すれば、fastbin を処理する
        if (have_fastchunks(av)) malloc_consolidate(av);
    }

```

### 大きなループ: unsorted bin の走査

**プログラムがここまで実行されたなら、chunk のサイズとちょうど一致する bin(fast bin、small bin)には、要求を直接満たせる chunk がなかったということです。ただし large chunk は、この大きなループの中で処理されます**。

以降のこのループでは、主に次の操作が行われます。

- FIFO の方式で、unsorted bin の chunk を 1 つずつ取り出す
    - small request であれば、ちょうど要求を満たすかを考え、満たせばそのまま返す。
    - そうでなければ、対応する bin に入れる。
- large bin からユーザーが必要とするメモリの確保を試みる

この部分は大きなループになっています。これは small bin chunk の再確保を試みるためです。まず large bin と top chunk で要求を満たそうとしますが、それでも満たせなかった場合、上で small bin の確保に成功しておらず、fast bin の chunk も統合していないため、ここで fast bin chunk の統合を行い、大きなループによって small bin chunk の確保をもう一度試みます。

```c++
    /*
       Process recently freed or remaindered chunks, taking one only if
       it is exact fit, or, if this a small request, the chunk is remainder from
       the most recent non-exact fit.  Place other traversed chunks in
       bins.  Note that this step is the only place in any routine where
       chunks are placed in bins.

       The outer loop here is needed because we might not realize until
       near the end of malloc that we should have consolidated, so must
       do so and retry. This happens at most once, and only when we would
       otherwise need to expand memory to service a "small" request.
     */

    for (;;) {
        int iters = 0;
```

#### unsorted bin の走査

まず unsorted bin を考え、次に last remainder を考えますが、small bin chunk の要求には例外があります。

**unsorted bin の走査順序は bk であることに注意してください。**

```c++
        // unsorted bin が空でなければ
        // First In First Out
        while ((victim = unsorted_chunks(av)->bk) != unsorted_chunks(av)) {
            // victim は unsorted bin の最後の chunk
            // bck は unsorted bin の末尾から 2 番目の chunk
            bck = victim->bk;
            // 得られた chunk が要求を満たすかを判断する。小さすぎても大きすぎてもいけない
            // 通常、system_mem の大きさは 132K
            if (__builtin_expect(chunksize_nomask(victim) <= 2 * SIZE_SZ, 0) ||
                __builtin_expect(chunksize_nomask(victim) > av->system_mem, 0))
                malloc_printerr(check_action, "malloc(): memory corruption",
                                chunk2mem(victim), av);
            // victim に対応する chunk のサイズを得る。
            size = chunksize(victim);
```

##### small request

ユーザーの要求が small bin chunk の場合、まず last remainder を考えます。last remainder が unsorted bin の中で唯一のブロックであり、かつ last remainder のサイズが分割後もなお 1 つの chunk として使える場合です。**なぜ等号がないのでしょうか**?

```c
            /*
               If a small request, try to use last remainder if it is the
               only chunk in unsorted bin.  This helps promote locality for
               runs of consecutive small requests. This is the only
               exception to best-fit, and applies only when there is
               no exact fit for a small chunk.
             */

            if (in_smallbin_range(nb) && bck == unsorted_chunks(av) &&
                victim == av->last_remainder &&
                (unsigned long) (size) > (unsigned long) (nb + MINSIZE)) {
                /* split and reattach remainder */
                // 新しい remainder のサイズを取得
                remainder_size          = size - nb;
                // 新しい remainder の位置を取得
                remainder               = chunk_at_offset(victim, nb);
                // unsorted bin の状態を更新
                unsorted_chunks(av)->bk = unsorted_chunks(av)->fd = remainder;
                // av に記録されている last_remainder を更新
                av->last_remainder                                = remainder;
                // last remainder のポインタを更新
                remainder->bk = remainder->fd = unsorted_chunks(av);
                if (!in_smallbin_range(remainder_size)) {
                    remainder->fd_nextsize = NULL;
                    remainder->bk_nextsize = NULL;
                }
                // victim のヘッダを設定、
                set_head(victim, nb | PREV_INUSE |
                                     (av != &main_arena ? NON_MAIN_ARENA : 0));
                // remainder のヘッダを設定
                set_head(remainder, remainder_size | PREV_INUSE);
                // remainder のサイズを記録する prev_size フィールドを設定する。このとき remainder は空き状態であるため。
                set_foot(remainder, remainder_size);
                // 詳細な検査。デバッグ時以外は効果がない
                check_malloced_chunk(av, victim, nb);
                // victim を chunk の形式から mem の形式に変換する
                void *p = chunk2mem(victim);
                // perturb_type が設定されていれば、取得した chunk を perturb_type ^ 0xff で初期化する
                alloc_perturb(p, bytes);
                return p;
            }
```

##### 最初の取り出し

```c
            /* remove from unsorted list */
            unsorted_chunks(av)->bk = bck;
            bck->fd                 = unsorted_chunks(av);
```

##### exact fit

unsorted bin から取り出した chunk のサイズがちょうど合っていれば、そのまま使います。ここでは、統合後にちょうど合うようになった chunk もすでに確保済みのはずです。

```c
            /* Take now instead of binning if exact fit */
            if (size == nb) {
                set_inuse_bit_at_offset(victim, size);
                if (av != &main_arena) set_non_main_arena(victim);
                check_malloced_chunk(av, victim, nb);
                void *p = chunk2mem(victim);
                alloc_perturb(p, bytes);
                return p;
            }
```

##### place chunk in small bin

取り出した chunk を、対応する small bin に入れます。

```c
            /* place chunk in bin */

            if (in_smallbin_range(size)) {
                victim_index = smallbin_index(size);
                bck          = bin_at(av, victim_index);
                fwd          = bck->fd;
```

##### place chunk in large bin

取り出した chunk を、対応する large bin に入れます。

```c
            } else {
                // large bin の範囲
                victim_index = largebin_index(size);
                bck          = bin_at(av, victim_index); // 現在の large bin の先頭
                fwd          = bck->fd;

                /* maintain large bins in sorted order */
                /* 从这里我们可以总结出，largebin 以 fd_nextsize 递减排序。
                   同样大小的 chunk，后来的只会插入到之前同样大小的 chunk 后，
                   而不会修改之前相同大小的fd/bk_nextsize，这也很容易理解，
                   可以减低开销。此外，bin 头不参与 nextsize 链接。*/
                // large bin のリストが空でなければ
                if (fwd != bck) {
                    /* Or with inuse bit to speed comparisons */
                    // 比較の高速化。おそらくそれだけが理由ではない。リスト内の chunk にはすべてこのビットが設定されているため。
                    size |= PREV_INUSE;
                    /* if smaller than smallest, bypass loop below */
                    // bck->bk には、対応する large bin の中で最小の chunk が格納されている。
                    // 走査中の chunk が現在の最小のものよりさらに小さければ、リストの末尾に挿入するだけでよい。
                    // bck->bk が main arena にあるかを判断する。
                    assert(chunk_main_arena(bck->bk));
                    if ((unsigned long) (size) <
                        (unsigned long) chunksize_nomask(bck->bk)) {
                        // fwd を large bin のヘッダに向ける
                        fwd = bck;
                        // bck を largin bin の末尾の chunk に向ける
                        bck = bck->bk;
                        // victim の fd_nextsize を largin bin の最初の chunk に向ける
                        victim->fd_nextsize = fwd->fd;
                        // victim の bk_nextsize を、元のリストの最初の chunk の bk_nextsize が指していたものに向ける
                        victim->bk_nextsize = fwd->fd->bk_nextsize;
                        // 元のリストの最初の chunk の bk_nextsize を victim に向ける
                        // 元のリストの最初の chunk を指していた fd_nextsize を victim に向ける
                        fwd->fd->bk_nextsize =
                            victim->bk_nextsize->fd_nextsize = victim;
                    } else {
                        // 今回挿入する victim のサイズが最小の chunk より大きい
                        // fwd が main arena にあるかを判断する
                        assert(chunk_main_arena(fwd));
                        // リストの先頭から、victim より大きくない chunk を探す
                        while ((unsigned long) size < chunksize_nomask(fwd)) {
                            fwd = fwd->fd_nextsize;
                            assert(chunk_main_arena(fwd));
                        }
                        // victim と同じ大きさの chunk が見つかったら、
                        // その chunk の後ろにそのまま挿入し、nextsize ポインタは変更しない。
                        if ((unsigned long) size ==
                            (unsigned long) chunksize_nomask(fwd))
                            /* Always insert in the second position.  */
                            fwd = fwd->fd;
                        else {
                            // 見つかった chunk が現在の victim とサイズが異なる場合
                            // nextsize の双方向リストを構築する必要がある
                            victim->fd_nextsize              = fwd;
                            victim->bk_nextsize              = fwd->bk_nextsize;
                            fwd->bk_nextsize                 = victim;
                            victim->bk_nextsize->fd_nextsize = victim;
                        }
                        bck = fwd->bk;
                    }
                } else
                    // 空であれば、単に fd_nextsize と bk_nextsize で双方向リストを構成すればよい。
                    victim->fd_nextsize = victim->bk_nextsize = victim;
            }
```

##### 最終的な取り出し

```c
            // 対応する bin に入れ、bck<-->victim<-->fwd を構成する。
            mark_bin(av, victim_index);
            victim->bk = bck;
            victim->fd = fwd;
            fwd->bk    = victim;
            bck->fd    = victim;
```

##### while の反復回数

while は最大 10000 回反復した後に終了します。

```c
            // #define MAX_ITERS 10000
            if (++iters >= MAX_ITERS) break;
        }
```

#### large chunk

**注: ここで先に small chunk が新しい要求を満たすかを確認しないのはなぜか、と不思議に思うかもしれません。これは small bin がループの前にすでに判定済みで、ここにあるとすれば、それは統合後に現れた chunk だからです。一方、大きなループの外では、large chunk は単にそのインデックスを調べただけなので、ここで先に判定するのは合理的であり、また下でさらに大きな chunk を探すためでもあります。**

要求された chunk が large chunk の範囲内であれば、対応する bin の中を小さい方から大きい方へ走査し、最初に合うものを見つけます。

```c++
        /*
           If a large request, scan through the chunks of current bin in
           sorted order to find smallest that fits.  Use the skip list for this.
         */
        if (!in_smallbin_range(nb)) {
            bin = bin_at(av, idx);
            /* skip scan if empty or largest chunk is too small */
            // 対応する bin が空、またはその中の最大の chunk でも小さいなら、スキップする
            // first(bin)=bin->fd は、現在のリストの中で最大の chunk を表す
            if ((victim = first(bin)) != bin &&
                (unsigned long) chunksize_nomask(victim) >=
                    (unsigned long) (nb)) {
                // リストを逆方向にたどり、必要な chunk サイズ以上の最初の chunk を見つける
                victim = victim->bk_nextsize;
                while (((unsigned long) (size = chunksize(victim)) <
                        (unsigned long) (nb)))
                    victim = victim->bk_nextsize;

                /* Avoid removing the first entry for a size so that the skip
                   list does not have to be rerouted.  */
                // 最終的に取得した chunk がその bin の最後の chunk でなく、かつその chunk が前の chunk と
                // 同じサイズなら、前の chunk を取る。そうすれば bk_nextsize と fd_nextsize の
                // リストを調整せずに済む。同じサイズの chunk は 1 つだけが nextsize のチェーンにつながれているため。
                if (victim != last(bin) &&
                    chunksize_nomask(victim) == chunksize_nomask(victim->fd))
                    victim = victim->fd;
                // 確保後に残るサイズを計算する
                remainder_size = size - nb;
                // unlink を行う
                unlink(av, victim, bck, fwd);

                /* Exhaust */
                // 残りのサイズが 1 つのブロックとして使うには足りない
                // このあとどうなるのか気になる?
                if (remainder_size < MINSIZE) {
                    set_inuse_bit_at_offset(victim, size);
                    if (av != &main_arena) set_non_main_arena(victim);
                }
                /* Split */
                // 残りのサイズが 1 つの chunk として使えるので、分割する。
                else {
                    // 残りの部分の chunk のポインタを取得する。これを remainder と呼ぶ
                    remainder = chunk_at_offset(victim, nb);
                    /* We cannot assume the unsorted list is empty and therefore
                       have to perform a complete insert here.  */
                    // unsorted bin に挿入する
                    bck = unsorted_chunks(av);
                    fwd = bck->fd;
                    // unsorted bin が壊されていないかを判断する。
                    if (__glibc_unlikely(fwd->bk != bck)) {
                        errstr = "malloc(): corrupted unsorted chunks";
                        goto errout;
                    }
                    remainder->bk = bck;
                    remainder->fd = fwd;
                    bck->fd       = remainder;
                    fwd->bk       = remainder;
                    // small bin の範囲内でなければ、対応するフィールドを設定する
                    if (!in_smallbin_range(remainder_size)) {
                        remainder->fd_nextsize = NULL;
                        remainder->bk_nextsize = NULL;
                    }
                    // 確保した chunk のフラグを設定する
                    set_head(victim,
                             nb | PREV_INUSE |
                                 (av != &main_arena ? NON_MAIN_ARENA : 0));

                    // remainder の前の chunk、つまり確保して渡した chunk の使用状態を設定する
                    // そのほかは気にしなくてよい。上から引き継がれているため
                    set_head(remainder, remainder_size | PREV_INUSE);
                    // remainder のサイズを設定する
                    set_foot(remainder, remainder_size);
                }
                // 検査
                check_malloced_chunk(av, victim, nb);
                // mem の状態に変換する
                void *p = chunk2mem(victim);
                // perturb_type が設定されていれば、取得した chunk を perturb_type ^ 0xff で初期化する
                alloc_perturb(p, bytes);
                return p;
            }
        }
```

#### より大きな chunk を探す

ここまで来たということは、ユーザーが必要とする chunk を、対応する適切な bin から直接取得できなかったということです。そのため、現在の bin より大きい fast bin、small bin、または large bin を探す必要があります。

```c++
        /*
           Search for a chunk by scanning bins, starting with next largest
           bin. This search is strictly by best-fit; i.e., the smallest
           (with ties going to approximately the least recently used) chunk
           that fits is selected.

           The bitmap avoids needing to check that most blocks are nonempty.
           The particular case of skipping all bins during warm-up phases
           when no chunks have been returned yet is faster than it might look.
         */

        ++idx;
        // 対応する bin を取得
        bin   = bin_at(av, idx);
        // 現在のインデックスの binmap における block のインデックスを取得
        // #define idx2block(i) ((i) >> BINMAPSHIFT)  ,BINMAPSHIFT=5
        // Binmap は block 単位で管理され、各 block は int 1 つ、計 32 ビットで、32 個の bin に空き chunk が存在するかを表せる
        // そのためここでは 5 ビット右シフトする
        block = idx2block(idx);
        // 現在のブロックサイズに対応するマップを取得する。ここから、対応する bin に空きブロックがあるかがわかる
        map   = av->binmap[ block ];
        // #define idx2bit(i) ((1U << ((i) & ((1U << BINMAPSHIFT) - 1))))
        // idx に対応するビットを 1 に、ほかのビットを 0 に設定する
        bit   = idx2bit(idx);
        for (;;) {
```

##### 適切な map を見つける

```c++
            /* Skip rest of block if there are no more set bits in this block.
             */
            // bit>map なら、その map には現在必要な chunk より大きい空きブロックがないことを表す
            // bit が 0 なら、上の idx2bit に渡した引数が 0 だったことを意味する。
            if (bit > map || bit == 0) {
                do {
                    // 次の block を探し、対応する map が 0 でなくなるまで続ける。
                    // すでに存在しなければ、top chunk を使うしかない
                    if (++block >= BINMAPSIZE) /* out of bins */
                        goto use_top;
                } while ((map = av->binmap[ block ]) == 0);
                // 対応する bin を取得する。その map の中の chunk のサイズはいずれも必要な chunk より大きく、かつ
                // map 自体が 0 でないため、要求を満たす chunk が必ず存在する。
                bin = bin_at(av, (block << BINMAPSHIFT));
                bit = 1;
            }
```

##### 適切な bin を見つける

```c
            /* Advance to bin with set bit. There must be one. */
            // 現在の map の最小の bin から、適切な bin が見つかるまで探す。
            // ここには必ず存在する
            while ((bit & map) == 0) {
                bin = next_bin(bin);
                bit <<= 1;
                assert(bit != 0);
            }
```

##### chunk の簡単な検査

```c
            /* Inspect the bin. It is likely to be non-empty */
            // 対応する bin を取得
            victim = last(bin);

            /*  If a false alarm (empty bin), clear the bit. */
            // victim=bin なら、map の対応するビットを 0 にクリアし、次の bin を取得する
            // このようなことが起こる確率はごく小さいはず。
            if (victim == bin) {
                av->binmap[ block ] = map &= ~bit; /* Write through */
                bin                 = next_bin(bin);
                bit <<= 1;
            }
```

##### 実際に chunk を取り出す

```c
            else {
                // 対応する victim のサイズを取得
                size = chunksize(victim);

                /*  We know the first chunk in this bin is big enough to use. */
                assert((unsigned long) (size) >= (unsigned long) (nb));
                // 分割後に残るサイズを計算
                remainder_size = size - nb;

                /* unlink */
                unlink(av, victim, bck, fwd);

                /* Exhaust */
                // 分割後に 1 つの chunk に足りなければどうするか?
                if (remainder_size < MINSIZE) {
                    set_inuse_bit_at_offset(victim, size);
                    if (av != &main_arena) set_non_main_arena(victim);
                }

                /* Split */
                // 足りるなら、分割する
                else {
                    // 残りの chunk のオフセットを計算
                    remainder = chunk_at_offset(victim, nb);

                    /* We cannot assume the unsorted list is empty and therefore
                       have to perform a complete insert here.  */
                    // 残りの chunk を unsorted bin に挿入
                    bck = unsorted_chunks(av);
                    fwd = bck->fd;
                    if (__glibc_unlikely(fwd->bk != bck)) {
                        errstr = "malloc(): corrupted unsorted chunks 2";
                        goto errout;
                    }
                    remainder->bk = bck;
                    remainder->fd = fwd;
                    bck->fd       = remainder;
                    fwd->bk       = remainder;

                    /* advertise as last remainder */
                    // small bin の範囲内なら、remainder として印を付ける
                    if (in_smallbin_range(nb)) av->last_remainder = remainder;
                    if (!in_smallbin_range(remainder_size)) {
                        remainder->fd_nextsize = NULL;
                        remainder->bk_nextsize = NULL;
                    }
                    // victim の使用状態を設定
                    set_head(victim,
                             nb | PREV_INUSE |
                                 (av != &main_arena ? NON_MAIN_ARENA : 0));
                    // remainder の使用状態を設定。これはなぜか?
                    set_head(remainder, remainder_size | PREV_INUSE);
                    // remainder のサイズを設定
                    set_foot(remainder, remainder_size);
                }
                // 検査
                check_malloced_chunk(av, victim, nb);
                // chunk の状態から mem の状態に変換
                void *p = chunk2mem(victim);
                // perturb_type が設定されていれば、取得した chunk を perturb_type ^ 0xff で初期化する
                alloc_perturb(p, bytes);
                return p;
            }
```

### top chunk を使う

すべての bin の chunk が要求を直接満たせない(つまり統合しない場合)、あるいはどれも空き chunk がない場合は、top chunk を使うしかありません。

```c++
    use_top:
        /*
           If large enough, split off the chunk bordering the end of memory
           (held in av->top). Note that this is in accord with the best-fit
           search rule.  In effect, av->top is treated as larger (and thus
           less well fitting) than any other available chunk since it can
           be extended to be as large as necessary (up to system
           limitations).

           We require that av->top always exists (i.e., has size >=
           MINSIZE) after initialization, so if it would otherwise be
           exhausted by current request, it is replenished. (The main
           reason for ensuring it exists is that we may need MINSIZE space
           to put in fenceposts in sysmalloc.)
         */
        // 現在の top chunk を取得し、その対応するサイズを計算
        victim = av->top;
        size   = chunksize(victim);
        // 分割後も top chunk のサイズが chunk の最小サイズを満たしていれば、そのまま分割できる。
        if ((unsigned long) (size) >= (unsigned long) (nb + MINSIZE)) {
            remainder_size = size - nb;
            remainder      = chunk_at_offset(victim, nb);
            av->top        = remainder;
            // ここで PREV_INUSE を設定するのは、top chunk の前の chunk が fastbin でなければ、必ず
            // top chunk と統合されるため、PREV_INUSE を設定している。
            set_head(victim, nb | PREV_INUSE |
                                 (av != &main_arena ? NON_MAIN_ARENA : 0));
            set_head(remainder, remainder_size | PREV_INUSE);

            check_malloced_chunk(av, victim, nb);
            void *p = chunk2mem(victim);
            alloc_perturb(p, bytes);
            return p;
        }
        // そうでなければ、fast chunk があるかを判断する
        /* When we are using atomic ops to free fast chunks we can get
           here for all block sizes.  */
        else if (have_fastchunks(av)) {
            // まず fast bin の統合を 1 回行う
            malloc_consolidate(av);
            /* restore original bin index */
            // 必要な chunk が small bin の範囲内か large bin の範囲内かを判断し、
            // 対応するインデックスを計算する
            // 次回にもう一度、使えるかを確認するのを待つ
            if (in_smallbin_range(nb))
                idx = smallbin_index(nb);
            else
                idx = largebin_index(nb);
        }

```

### ヒープメモリが足りない

ヒープメモリが足りない場合は、`sysmalloc` を使ってメモリを確保する必要があります。

```c
        /*
           Otherwise, relay to handle system-dependent cases
         */
        // そうでなければ、システムからもう少しメモリを確保するしかない。
        else {
            void *p = sysmalloc(nb, av);
            if (p != NULL) alloc_perturb(p, bytes);
            return p;
        }
```



## _libc_calloc

calloc も libc におけるメモリブロック確保関数の 1 つです。`libc` 内でのラッパーは `_libc_calloc` で、具体的な説明は次のとおりです。

```c
/*
  calloc(size_t n_elements, size_t element_size);
  Returns a pointer to n_elements * element_size bytes, with all locations
  set to zero.
*/
void*  __libc_calloc(size_t, size_t);
```

## sysmalloc

この関数のヘッダのコメントにあるように、この関数は、現在のヒープメモリが足りないときに、システムからさらにメモリを要求するために使われます。

```c
/*
   sysmalloc handles malloc cases requiring more memory from the system.
   On entry, it is assumed that av->top does not have enough
   space to service request for nb bytes, thus requiring that av->top
   be extended or replaced.
 */
```

### 基本的な定義

```c
static void *sysmalloc(INTERNAL_SIZE_T nb, mstate av) {
  mchunkptr old_top;        /* incoming value of av->top */
  INTERNAL_SIZE_T old_size; /* its size */
  char *old_end;            /* its end address */

  long size; /* arg to first MORECORE or mmap call */
  char *brk; /* return value from MORECORE */

  long correction; /* arg to 2nd MORECORE call */
  char *snd_brk;   /* 2nd return val */

  INTERNAL_SIZE_T front_misalign; /* unusable bytes at front of new space */
  INTERNAL_SIZE_T end_misalign;   /* partial page left at end of new space */
  char *aligned_brk;              /* aligned offset into brk */

  mchunkptr p;                  /* the allocated/returned chunk */
  mchunkptr remainder;          /* remainder frOm allocation */
  unsigned long remainder_size; /* its size */

  size_t pagesize = GLRO(dl_pagesize);
  bool tried_mmap = false;
```

主に `pagesize` に注目します。その定義は次のとおりです。

```c
#ifndef EXEC_PAGESIZE
#define EXEC_PAGESIZE	4096
#endif
# define GLRO(name) _##name
size_t _dl_pagesize = EXEC_PAGESIZE;
```

したがって、`pagesize=4096=0x1000` です。

### mmap を考える

冒頭のコメントにあるように、次のいずれかの条件を満たす場合です。

1. ヒープが確保されていない。
2. 要求されたメモリが `mp_.mmap_threshold` より大きく、かつ mmap の数が最大値より小さければ、mmap を使ってみることができる。

デフォルトでは、しきい値は次のとおりです。

```c
static struct malloc_par mp_ = {
    .top_pad = DEFAULT_TOP_PAD,
    .n_mmaps_max = DEFAULT_MMAP_MAX,
    .mmap_threshold = DEFAULT_MMAP_THRESHOLD,
    .trim_threshold = DEFAULT_TRIM_THRESHOLD,
#define NARENAS_FROM_NCORES(n) ((n) * (sizeof(long) == 4 ? 2 : 8))
    .arena_test = NARENAS_FROM_NCORES(1)
#if USE_TCACHE
        ,
    .tcache_count = TCACHE_FILL_COUNT,
    .tcache_bins = TCACHE_MAX_BINS,
    .tcache_max_bytes = tidx2usize(TCACHE_MAX_BINS - 1),
    .tcache_unsorted_limit = 0 /* No limit.  */
#endif
};
```

`DEFAULT_MMAP_THRESHOLD` は 128*1024 バイト、つまり 128 K です。

```c
#ifndef DEFAULT_MMAP_THRESHOLD
#define DEFAULT_MMAP_THRESHOLD DEFAULT_MMAP_THRESHOLD_MIN
#endif
/*
  MMAP_THRESHOLD_MAX and _MIN are the bounds on the dynamically
  adjusted MMAP_THRESHOLD.
*/

#ifndef DEFAULT_MMAP_THRESHOLD_MIN
#define DEFAULT_MMAP_THRESHOLD_MIN (128 * 1024)
#endif

#ifndef DEFAULT_MMAP_THRESHOLD_MAX
/* For 32-bit platforms we cannot increase the maximum mmap
   threshold much because it is also the minimum value for the
   maximum heap size and its alignment.  Going above 512k (i.e., 1M
   for new heaps) wastes too much address space.  */
#if __WORDSIZE == 32
#define DEFAULT_MMAP_THRESHOLD_MAX (512 * 1024)
#else
#define DEFAULT_MMAP_THRESHOLD_MAX (4 * 1024 * 1024 * sizeof(long))
#endif
#endif
```

以下はこの部分のコードです。今は重点ではないので、いったん読み飛ばしてかまいません。

```c
  /*
     If have mmap, and the request size meets the mmap threshold, and
     the system supports mmap, and there are few enough currently
     allocated mmapped regions, try to directly map this request
     rather than expanding top.
   */

  if (av == NULL ||
      ((unsigned long)(nb) >= (unsigned long)(mp_.mmap_threshold) &&
       (mp_.n_mmaps < mp_.n_mmaps_max))) {
    char *mm; /* return value from mmap call*/

  try_mmap:
    /*
       Round up size to nearest page.  For mmapped chunks, the overhead
       is one SIZE_SZ unit larger than for normal chunks, because there
       is no following chunk whose prev_size field could be used.

       See the front_misalign handling below, for glibc there is no
       need for further alignments unless we have have high alignment.
     */
    if (MALLOC_ALIGNMENT == 2 * SIZE_SZ)
      size = ALIGN_UP(nb + SIZE_SZ, pagesize);
    else
      size = ALIGN_UP(nb + SIZE_SZ + MALLOC_ALIGN_MASK, pagesize);
    tried_mmap = true;

    /* Don't try if size wraps around 0 */
    if ((unsigned long)(size) > (unsigned long)(nb)) {
      mm = (char *)(MMAP(0, size, PROT_READ | PROT_WRITE, 0));

      if (mm != MAP_FAILED) {
        /*
           The offset to the start of the mmapped region is stored
           in the prev_size field of the chunk. This allows us to adjust
           returned start address to meet alignment requirements here
           and in memalign(), and still be able to compute proper
           address argument for later munmap in free() and realloc().
         */

        if (MALLOC_ALIGNMENT == 2 * SIZE_SZ) {
          /* For glibc, chunk2mem increases the address by 2*SIZE_SZ and
             MALLOC_ALIGN_MASK is 2*SIZE_SZ-1.  Each mmap'ed area is page
             aligned and therefore definitely MALLOC_ALIGN_MASK-aligned.  */
          assert(((INTERNAL_SIZE_T)chunk2mem(mm) & MALLOC_ALIGN_MASK) == 0);
          front_misalign = 0;
        } else
          front_misalign = (INTERNAL_SIZE_T)chunk2mem(mm) & MALLOC_ALIGN_MASK;
        if (front_misalign > 0) {
          correction = MALLOC_ALIGNMENT - front_misalign;
          p = (mchunkptr)(mm + correction);
          set_prev_size(p, correction);
          set_head(p, (size - correction) | IS_MMAPPED);
        } else {
          p = (mchunkptr)mm;
          set_prev_size(p, 0);
          set_head(p, size | IS_MMAPPED);
        }

        /* update statistics */

        int new = atomic_exchange_and_add(&mp_.n_mmaps, 1) + 1;
        atomic_max(&mp_.max_n_mmaps, new);

        unsigned long sum;
        sum = atomic_exchange_and_add(&mp_.mmapped_mem, size) + size;
        atomic_max(&mp_.max_mmapped_mem, sum);

        check_chunk(av, p);

        return chunk2mem(p);
      }
    }
  }
```

### mmap の失敗、またはヒープが未確保

```c
  /* There are no usable arenas and mmap also failed.  */
  if (av == NULL)
    return 0;
```

この 2 つの場合のどちらかであれば、実はここで終了できます。。

### 古いヒープ情報の記録

```c
  /* Record incoming configuration of top */

  old_top = av->top;
  old_size = chunksize(old_top);
  old_end = (char *)(chunk_at_offset(old_top, old_size));

  brk = snd_brk = (char *)(MORECORE_FAILURE);
```

### 古いヒープ情報の検査 1

```c
  /*
     If not the first time through, we require old_size to be
     at least MINSIZE and to have prev_inuse set.
   */

  assert((old_top == initial_top(av) && old_size == 0) ||
         ((unsigned long)(old_size) >= MINSIZE && prev_inuse(old_top) &&
          ((unsigned long)old_end & (pagesize - 1)) == 0));
```

この検査は、次のいずれかの条件を満たす必要があります。

1. `old_top == initial_top(av) && old_size == 0`、つまり最初の場合、ヒープのサイズは 0 でなければならない。
2. 新しいヒープの場合は、次のとおり。
    1. `(unsigned long)(old_size) >= MINSIZE && prev_inuse(old_top)`、ヒープのサイズは `MINSIZE` 以上でなければならず、かつ直前のヒープチャンクが使用中でなければならない。
    2. `((unsigned long)old_end & (pagesize - 1)) == 0)`、ヒープの終了アドレスはページにアラインされていなければならない。ページアラインのサイズはデフォルトで 0x1000 なので、下位 12 ビットは 0 でなければならない。

### 古いヒープ情報の検査 2

```c
  /* Precondition: not enough current space to satisfy nb request */
  assert((unsigned long)(old_size) < (unsigned long)(nb + MINSIZE));
```

malloc での定義によると、

```c
static void *_int_malloc(mstate av, size_t bytes) {
    INTERNAL_SIZE_T nb;  /* normalized request size */
```

`nb` はすでに chunk ヘッダのバイト数を加えたものであるはずなのに、なぜさらに `MINSIZE ` を加えるのでしょうか。これは、top chunk のサイズには少なくとも MINSIZE の領域を残しておく必要があり、統合しやすくするためです。

### main_arena でない場合

ここは今のところ重点ではないので、いったん分析しません。

```c
  if (av != &main_arena) {
    heap_info *old_heap, *heap;
    size_t old_heap_size;

    /* First try to extend the current heap. */
    old_heap = heap_for_ptr(old_top);
    old_heap_size = old_heap->size;
    if ((long)(MINSIZE + nb - old_size) > 0 &&
        grow_heap(old_heap, MINSIZE + nb - old_size) == 0) {
      av->system_mem += old_heap->size - old_heap_size;
      set_head(old_top,
               (((char *)old_heap + old_heap->size) - (char *)old_top) |
                   PREV_INUSE);
    } else if ((heap = new_heap(nb + (MINSIZE + sizeof(*heap)), mp_.top_pad))) {
      /* Use a newly allocated heap.  */
      heap->ar_ptr = av;
      heap->prev = old_heap;
      av->system_mem += heap->size;
      /* Set up the new top.  */
      top(av) = chunk_at_offset(heap, sizeof(*heap));
      set_head(top(av), (heap->size - sizeof(*heap)) | PREV_INUSE);

      /* Setup fencepost and free the old top chunk with a multiple of
         MALLOC_ALIGNMENT in size. */
      /* The fencepost takes at least MINSIZE bytes, because it might
         become the top chunk again later.  Note that a footer is set
         up, too, although the chunk is marked in use. */
      old_size = (old_size - MINSIZE) & ~MALLOC_ALIGN_MASK;
      set_head(chunk_at_offset(old_top, old_size + 2 * SIZE_SZ),
               0 | PREV_INUSE);
      if (old_size >= MINSIZE) {
        set_head(chunk_at_offset(old_top, old_size),
                 (2 * SIZE_SZ) | PREV_INUSE);
        set_foot(chunk_at_offset(old_top, old_size), (2 * SIZE_SZ));
        set_head(old_top, old_size | PREV_INUSE | NON_MAIN_ARENA);
        _int_free(av, old_top, 1);
      } else {
        set_head(old_top, (old_size + 2 * SIZE_SZ) | PREV_INUSE);
        set_foot(old_top, (old_size + 2 * SIZE_SZ));
      }
    } else if (!tried_mmap)
      /* We can at least try to use to mmap memory.  */
      goto try_mmap;
  }
```

### Main_arena の処理

#### メモリの計算

要求を満たせるメモリサイズを計算します。

```c
else { /* av == main_arena */

    /* Request enough space for nb + pad + overhead */
    size = nb + mp_.top_pad + MINSIZE;
```

デフォルトでは `top_pad` は次のように定義されています。

```c
#ifndef DEFAULT_TOP_PAD
# define DEFAULT_TOP_PAD 131072
#endif
```

つまり 131072 バイト、0x20000 バイトです。

#### 連続しているか

ヒープの領域を連続させたい場合は、以前のメモリを再利用できます。

```c
    /*
       If contiguous, we can subtract out existing space that we hope to
       combine with new space. We add it back later only if
       we don't actually get contiguous space.
     */

    if (contiguous(av))
      size -= old_size;
```

#### ページサイズへのアライン

```c
    /*
       Round to a multiple of page size.
       If MORECORE is not contiguous, this ensures that we only call it
       with whole-page arguments.  And if MORECORE is contiguous and
       this is not first time through, this preserves page-alignment of
       previous calls. Otherwise, we correct to page-align below.
     */

    size = ALIGN_UP(size, pagesize);
```

#### メモリの確保

```c
    /*
       Don't try to call MORECORE if argument is so big as to appear
       negative. Note that since mmap takes size_t arg, it may succeed
       below even if we cannot call MORECORE.
     */

    if (size > 0) {
      brk = (char *)(MORECORE(size));
      LIBC_PROBE(memory_sbrk_more, 2, brk, size);
    }
```

##### 成功する可能性がある場合

```c
    if (brk != (char *)(MORECORE_FAILURE)) {
      /* Call the `morecore' hook if necessary.  */
      void (*hook)(void) = atomic_forced_read(__after_morecore_hook);
      if (__builtin_expect(hook != NULL, 0))
        (*hook)();
    }
```

ここでフックが呼び出されているのは、ちょっと面白いです。

##### 失敗

失敗した場合は、mmap を考えます。

```c
else {
      /*
         If have mmap, try using it as a backup when MORECORE fails or
         cannot be used. This is worth doing on systems that have "holes" in
         address space, so sbrk cannot extend to give contiguous space, but
         space is available elsewhere.  Note that we ignore mmap max count
         and threshold limits, since the space will not be used as a
         segregated mmap region.
       */

      /* Cannot merge with old top, so add its size back in */
      if (contiguous(av))
        size = ALIGN_UP(size + old_size, pagesize);

      /* If we are relying on mmap as backup, then use larger units */
      if ((unsigned long)(size) < (unsigned long)(MMAP_AS_MORECORE_SIZE))
        size = MMAP_AS_MORECORE_SIZE;

      /* Don't try if size wraps around 0 */
      if ((unsigned long)(size) > (unsigned long)(nb)) {
        char *mbrk = (char *)(MMAP(0, size, PROT_READ | PROT_WRITE, 0));

        if (mbrk != MAP_FAILED) {
          /* We do not need, and cannot use, another sbrk call to find end */
          brk = mbrk;
          snd_brk = brk + size;

          /*
             Record that we no longer have a contiguous sbrk region.
             After the first time mmap is used as backup, we do not
             ever rely on contiguous space since this could incorrectly
             bridge regions.
           */
          set_noncontiguous(av);
        }
      }
    }
```

#### メモリの確保に成功した可能性がある場合

```c
    if (brk != (char *)(MORECORE_FAILURE)) {
      if (mp_.sbrk_base == 0)
        mp_.sbrk_base = brk;
      av->system_mem += size;
```

##### ケース 1

```c
      /*
         If MORECORE extends previous space, we can likewise extend top size.
       */

      if (brk == old_end && snd_brk == (char *)(MORECORE_FAILURE))
        set_head(old_top, (size + old_size) | PREV_INUSE);
```

##### ケース 2: 予期しないメモリ枯渇

```c
      else if (contiguous(av) && old_size && brk < old_end)
        /* Oops!  Someone else killed our space..  Can't touch anything.  */
        malloc_printerr("break adjusted to free malloc space");
```

##### その他の予期しない状況の処理

```c
      /*
         Otherwise, make adjustments:

       * If the first time through or noncontiguous, we need to call sbrk
          just to find out where the end of memory lies.

       * We need to ensure that all returned chunks from malloc will meet
          MALLOC_ALIGNMENT

       * If there was an intervening foreign sbrk, we need to adjust sbrk
          request size to account for fact that we will not be able to
          combine new space with existing space in old_top.

       * Almost all systems internally allocate whole pages at a time, in
          which case we might as well use the whole last page of request.
          So we allocate enough more memory to hit a page boundary now,
          which in turn causes future contiguous calls to page-align.
       */

      else {
        front_misalign = 0;
        end_misalign = 0;
        correction = 0;
        aligned_brk = brk;
```

###### 連続したメモリの処理

```c
        /* handle contiguous cases */
        if (contiguous(av)) {
          /* Count foreign sbrk as system_mem.  */
          if (old_size)
            av->system_mem += brk - old_end;

          /* Guarantee alignment of first new chunk made from this space */

          front_misalign = (INTERNAL_SIZE_T)chunk2mem(brk) & MALLOC_ALIGN_MASK;
          if (front_misalign > 0) {
            /*
               Skip over some bytes to arrive at an aligned position.
               We don't need to specially mark these wasted front bytes.
               They will never be accessed anyway because
               prev_inuse of av->top (and any chunk created from its start)
               is always true after initialization.
             */

            correction = MALLOC_ALIGNMENT - front_misalign;
            aligned_brk += correction;
          }

          /*
             If this isn't adjacent to existing space, then we will not
             be able to merge with old_top space, so must add to 2nd request.
           */

          correction += old_size;

          /* Extend the end address to hit a page boundary */
          end_misalign = (INTERNAL_SIZE_T)(brk + size + correction);
          correction += (ALIGN_UP(end_misalign, pagesize)) - end_misalign;

          assert(correction >= 0);
          snd_brk = (char *)(MORECORE(correction));

          /*
             If can't allocate correction, try to at least find out current
             brk.  It might be enough to proceed without failing.

             Note that if second sbrk did NOT fail, we assume that space
             is contiguous with first sbrk. This is a safe assumption unless
             program is multithreaded but doesn't use locks and a foreign sbrk
             occurred between our first and second calls.
           */

          if (snd_brk == (char *)(MORECORE_FAILURE)) {
            correction = 0;
            snd_brk = (char *)(MORECORE(0));
          } else {
            /* Call the `morecore' hook if necessary.  */
            void (*hook)(void) = atomic_forced_read(__after_morecore_hook);
            if (__builtin_expect(hook != NULL, 0))
              (*hook)();
          }
        }
```

###### 連続していないメモリの処理

```c
        /* handle non-contiguous cases */
        else {
          if (MALLOC_ALIGNMENT == 2 * SIZE_SZ)
            /* MORECORE/mmap must correctly align */
            assert(((unsigned long)chunk2mem(brk) & MALLOC_ALIGN_MASK) == 0);
          else {
            front_misalign =
                (INTERNAL_SIZE_T)chunk2mem(brk) & MALLOC_ALIGN_MASK;
            if (front_misalign > 0) {
              /*
                 Skip over some bytes to arrive at an aligned position.
                 We don't need to specially mark these wasted front bytes.
                 They will never be accessed anyway because
                 prev_inuse of av->top (and any chunk created from its start)
                 is always true after initialization.
               */

              aligned_brk += MALLOC_ALIGNMENT - front_misalign;
            }
          }

          /* Find out current end of memory */
          if (snd_brk == (char *)(MORECORE_FAILURE)) {
            snd_brk = (char *)(MORECORE(0));
          }
        }
```

###### 調整

```c
        /* Adjust top based on results of second sbrk */
        if (snd_brk != (char *)(MORECORE_FAILURE)) {
          av->top = (mchunkptr)aligned_brk;
          set_head(av->top, (snd_brk - aligned_brk + correction) | PREV_INUSE);
          av->system_mem += correction;

          /*
             If not the first time through, we either have a
             gap due to foreign sbrk or a non-contiguous region.  Insert a
             double fencepost at old_top to prevent consolidation with space
             we don't own. These fenceposts are artificial chunks that are
             marked as inuse and are in any case too small to use.  We need
             two to make sizes and alignments work out.
           */

          if (old_size != 0) {
            /*
               Shrink old_top to insert fenceposts, keeping size a
               multiple of MALLOC_ALIGNMENT. We know there is at least
               enough space in old_top to do this.
             */
            old_size = (old_size - 4 * SIZE_SZ) & ~MALLOC_ALIGN_MASK;
            set_head(old_top, old_size | PREV_INUSE);

            /*
               Note that the following assignments completely overwrite
               old_top when old_size was previously MINSIZE.  This is
               intentional. We need the fencepost, even if old_top otherwise
               gets lost.
             */
            set_head(chunk_at_offset(old_top, old_size),
                     (2 * SIZE_SZ) | PREV_INUSE);
            set_head(chunk_at_offset(old_top, old_size + 2 * SIZE_SZ),
                     (2 * SIZE_SZ) | PREV_INUSE);

            /* If possible, release the rest. */
            if (old_size >= MINSIZE) {
              _int_free(av, old_top, 1);
            }
          }
        }
      }
```

ここでプログラムが古い top chunk を解放していることに注意してください。そのため、サイズに応じて異なる bin や tcache に入ります。

#### 最大メモリの更新

```c
  if ((unsigned long)av->system_mem > (unsigned long)(av->max_system_mem))
    av->max_system_mem = av->system_mem;
  check_malloc_state(av);
```

#### メモリブロックの確保

##### サイズの取得

```c
  /* finally, do the allocation */
  p = av->top;
  size = chunksize(p);
```

##### top の切り分け

```c
  /* check that one of the above allocation paths succeeded */
  if ((unsigned long)(size) >= (unsigned long)(nb + MINSIZE)) {
    remainder_size = size - nb;
    remainder = chunk_at_offset(p, nb);
    av->top = remainder;
    set_head(p, nb | PREV_INUSE | (av != &main_arena ? NON_MAIN_ARENA : 0));
    set_head(remainder, remainder_size | PREV_INUSE);
    check_malloced_chunk(av, p, nb);
    return chunk2mem(p);
  }
```

#### すべてのエラーの捕捉

```c
  /* catch all failure paths */
  __set_errno(ENOMEM);
  return 0;
```

