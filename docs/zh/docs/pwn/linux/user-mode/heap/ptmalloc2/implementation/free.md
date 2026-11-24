# メモリブロックの解放

## __libc_free

malloc と同様に、free 関数にも 1 層のラッパーがあり、命名形式は malloc とほぼ同じです。コードは次のとおりです。

```c++
void __libc_free(void *mem) {
    mstate    ar_ptr;
    mchunkptr p; /* chunk corresponding to mem */
    // フック関数 __free_hook があるかを判断する
    void (*hook)(void *, const void *) = atomic_forced_read(__free_hook);
    if (__builtin_expect(hook != NULL, 0)) {
        (*hook)(mem, RETURN_ADDRESS(0));
        return;
    }
    // free NULL は何もしない
    if (mem == 0) /* free(0) has no effect */
        return;
    // mem を chunk の状態に変換する
    p = mem2chunk(mem);
    // このメモリブロックが mmap で得られたものである場合
    if (chunk_is_mmapped(p)) /* release mmapped memory. */
    {
        /* See if the dynamic brk/mmap threshold needs adjusting.
       Dumped fake mmapped chunks do not affect the threshold.  */
        if (!mp_.no_dyn_threshold && chunksize_nomask(p) > mp_.mmap_threshold &&
            chunksize_nomask(p) <= DEFAULT_MMAP_THRESHOLD_MAX &&
            !DUMPED_MAIN_ARENA_CHUNK(p)) {
            mp_.mmap_threshold = chunksize(p);
            mp_.trim_threshold = 2 * mp_.mmap_threshold;
            LIBC_PROBE(memory_mallopt_free_dyn_thresholds, 2,
                       mp_.mmap_threshold, mp_.trim_threshold);
        }
        munmap_chunk(p);
        return;
    }
    // chunk から arena のポインタを取得する
    ar_ptr = arena_for_chunk(p);
    // 解放を実行する
    _int_free(ar_ptr, p, 0);
}
```

## _int_free

関数の冒頭で一連の変数が定義され、ユーザーが解放しようとしている chunk のサイズが得られます。

```c++
static void _int_free(mstate av, mchunkptr p, int have_lock) {
    INTERNAL_SIZE_T size;      /* its size */
    mfastbinptr *   fb;        /* associated fastbin */
    mchunkptr       nextchunk; /* next contiguous chunk */
    INTERNAL_SIZE_T nextsize;  /* its size */
    int             nextinuse; /* true if nextchunk is used */
    INTERNAL_SIZE_T prevsize;  /* size of previous contiguous chunk */
    mchunkptr       bck;       /* misc temp for linking */
    mchunkptr       fwd;       /* misc temp for linking */

    const char *errstr = NULL;
    int         locked = 0;

    size = chunksize(p);
```

### 簡単な検査

```c++
    /* Little security check which won't hurt performance: the
       allocator never wrapps around at the end of the address space.
       Therefore we can exclude some size values which might appear
       here by accident or by "design" from some intruder.  */
    // ポインタは不正なアドレスを指してはならず、-size 以下でなければならない。なぜか?
    // ポインタはアラインされていなければならない。2*SIZE_SZ のアラインについてはよく考える必要がある
    if (__builtin_expect((uintptr_t) p > (uintptr_t) -size, 0) ||
        __builtin_expect(misaligned_chunk(p), 0)) {
        errstr = "free(): invalid pointer";
    errout:
        if (!have_lock && locked) __libc_lock_unlock(av->mutex);
        malloc_printerr(check_action, errstr, chunk2mem(p), av);
        return;
    }
    /* We know that each chunk is at least MINSIZE bytes in size or a
       multiple of MALLOC_ALIGNMENT.  */
    // サイズが最小の chunk より小さい、または MALLOC_ALIGNMENT の整数倍でない
    if (__glibc_unlikely(size < MINSIZE || !aligned_OK(size))) {
        errstr = "free(): invalid size";
        goto errout;
    }
    // この chunk が使用中かどうかを検査する。デバッグ時以外は効果がない
    check_inuse_chunk(av, p);
```

このうち

```c
/* Check if m has acceptable alignment */

#define aligned_OK(m) (((unsigned long) (m) &MALLOC_ALIGN_MASK) == 0)

#define misaligned_chunk(p)                                                    \
    ((uintptr_t)(MALLOC_ALIGNMENT == 2 * SIZE_SZ ? (p) : chunk2mem(p)) &       \
     MALLOC_ALIGN_MASK)
```



### fast bin

上記の検査がすべて合格した場合、現在の bin が fast bin の範囲内かどうかを判断し、範囲内であれば **fastbin の先頭**に挿入します。つまり、対応する fastbin リストの**最初の free chunk** になります。

```c++
    /*
      If eligible, place chunk on a fastbin so it can be found
      and used quickly in malloc.
    */

    if ((unsigned long) (size) <= (unsigned long) (get_max_fast())

#if TRIM_FASTBINS
        /*
      If TRIM_FASTBINS set, don't place chunks
      bordering top into fastbins
        */
       //デフォルトでは #define TRIM_FASTBINS 0 なので、デフォルトでは以下の文は実行されない
       // 現在の chunk が fast chunk で、次の chunk が top chunk なら、挿入できない
        && (chunk_at_offset(p, size) != av->top)
#endif
            ) {
        // 次の chunk のサイズは SIZE_SZ の 2 倍以下であってはならず、かつ
        // 次の chunk のサイズは system_mem 以上であってはならない。通常は 132k
        // このような場合はエラーとする。
        if (__builtin_expect(
                chunksize_nomask(chunk_at_offset(p, size)) <= 2 * SIZE_SZ, 0) ||
            __builtin_expect(
                chunksize(chunk_at_offset(p, size)) >= av->system_mem, 0)) {
            /* We might not have a lock at this point and concurrent
               modifications
               of system_mem might have let to a false positive.  Redo the test
               after getting the lock.  */
            if (have_lock || ({
                    assert(locked == 0);
                    __libc_lock_lock(av->mutex);
                    locked = 1;
                    chunksize_nomask(chunk_at_offset(p, size)) <= 2 * SIZE_SZ ||
                        chunksize(chunk_at_offset(p, size)) >= av->system_mem;
                })) {
                errstr = "free(): invalid next size (fast)";
                goto errout;
            }
            if (!have_lock) {
                __libc_lock_unlock(av->mutex);
                locked = 0;
            }
        }
        // chunk の mem 部分をすべて perturb_byte に設定する
        free_perturb(chunk2mem(p), size - 2 * SIZE_SZ);
        // fast chunk のフラグビットを設定する
        set_fastchunks(av);
        // サイズから fast bin のインデックスを取得する
        unsigned int idx = fastbin_index(size);
        // 対応する fastbin の先頭ポインタを取得する。初期化後は NULL
        fb               = &fastbin(av, idx);

        /* Atomically link P to its fastbin: P->FD = *FB; *FB = P;  */
        // アトミック操作で P をリストに挿入する
        mchunkptr    old     = *fb, old2;
        unsigned int old_idx = ~0u;
        do {
            /* Check that the top of the bin is not the record we are going to
               add
               (i.e., double free).  */
            // so we can not double free one fastbin chunk
            // fast bin に対する double free を防ぐ
            if (__builtin_expect(old == p, 0)) {
                errstr = "double free or corruption (fasttop)";
                goto errout;
            }
            /* Check that size of fastbin chunk at the top is the same as
               size of the chunk that we are adding.  We can dereference OLD
               only if we have the lock, otherwise it might have already been
               deallocated.  See use of OLD_IDX below for the actual check.  */
            if (have_lock && old != NULL)
                old_idx = fastbin_index(chunksize(old));
            p->fd = old2 = old;
        } while ((old = catomic_compare_and_exchange_val_rel(fb, p, old2)) !=
                 old2);
        // fast bin への追加の前後で同じであることを確認する
        if (have_lock && old != NULL && __builtin_expect(old_idx != idx, 0)) {
            errstr = "invalid fastbin entry (free)";
            goto errout;
        }
    }
```

### mmap でない空き chunk の統合

**fast bin でない場合にのみ unlink が発動します**

まず、なぜ chunk を統合するのかを説明します。これは、ヒープ中に細々としたメモリブロックが多くなりすぎるのを避けるためで、統合後はより大きなメモリブロックの要求に対応できます。統合の順序は主に次のとおりです。

- まず、物理的に低位アドレスの空きブロックを考慮する
- 次に、物理的に高位アドレスの空きブロックを考慮する

**統合後の chunk は、統合された chunk の低位アドレスを指します。**

ロックを取得していない場合は、まずロックを取得します。

```c++
    /*
      Consolidate other non-mmapped chunks as they arrive.
    */

    else if (!chunk_is_mmapped(p)) {
        if (!have_lock) {
            __libc_lock_lock(av->mutex);
            locked = 1;
        }
        nextchunk = chunk_at_offset(p, size);
```

#### 軽量な検査

```c++
        /* Lightweight tests: check whether the block is already the
           top block.  */
        // 現在 free する chunk は top chunk であってはならない
        if (__glibc_unlikely(p == av->top)) {
            errstr = "double free or corruption (top)";
            goto errout;
        }
        // 現在 free する chunk の次の chunk は arena の境界を越えてはならない
        /* Or whether the next chunk is beyond the boundaries of the arena.  */
        if (__builtin_expect(contiguous(av) &&
                                 (char *) nextchunk >=
                                     ((char *) av->top + chunksize(av->top)),
                             0)) {
            errstr = "double free or corruption (out)";
            goto errout;
        }
        // 現在 free しようとする chunk の使用フラグが立っていない。double free
        /* Or whether the block is actually not marked used.  */
        if (__glibc_unlikely(!prev_inuse(nextchunk))) {
            errstr = "double free or corruption (!prev)";
            goto errout;
        }
        // 次の chunk のサイズ
        nextsize = chunksize(nextchunk);
        // next chunk size valid check
        // 次の chunk のサイズが 2*SIZE_SZ 以下か、または
        // nextsize がシステムの提供できるメモリ以上かを判断する
        if (__builtin_expect(chunksize_nomask(nextchunk) <= 2 * SIZE_SZ, 0) ||
            __builtin_expect(nextsize >= av->system_mem, 0)) {
            errstr = "free(): invalid next size (normal)";
            goto errout;
        }
```

#### 解放時のパディング

```c++
        //ポインタの mem 部分をすべて perturb_byte に設定する
		free_perturb(chunk2mem(p), size - 2 * SIZE_SZ);
```

#### 後方統合: 低位アドレスの chunk を統合

```c++
        /* consolidate backward */
        if (!prev_inuse(p)) {
            prevsize = prev_size(p);
            size += prevsize;
            p = chunk_at_offset(p, -((long) prevsize));
            unlink(av, p, bck, fwd);
        }
```

#### 次のブロックが top chunk でない場合: 前方統合、高位アドレスの chunk を統合

次のブロックが top chunk でない場合は、高位アドレスの chunk を統合し、統合後の chunk を unsorted bin に入れることに注意してください。

```c++
		// 次の chunk が top chunk でない場合
		if (nextchunk != av->top) {
            /* get and clear inuse bit */
            // 次の chunk の使用状態を取得する
            nextinuse = inuse_bit_at_offset(nextchunk, nextsize);
            // 使用中でなければ統合し、そうでなければ現在の chunk の使用状態をクリアする。
            /* consolidate forward */
            if (!nextinuse) {
                unlink(av, nextchunk, bck, fwd);
                size += nextsize;
            } else
                clear_inuse_bit_at_offset(nextchunk, 0);

            /*
          Place the chunk in unsorted chunk list. Chunks are
          not placed into regular bins until after they have
          been given one chance to be used in malloc.
            */
            // chunk を unsorted chunk リストの先頭に置く
            bck = unsorted_chunks(av);
            fwd = bck->fd;
            // 簡単な検査
            if (__glibc_unlikely(fwd->bk != bck)) {
                errstr = "free(): corrupted unsorted chunks";
                goto errout;
            }
            p->fd = fwd;
            p->bk = bck;
            // large chunk なら、nextsize ポインタフィールドを NULL に設定する。
            if (!in_smallbin_range(size)) {
                p->fd_nextsize = NULL;
                p->bk_nextsize = NULL;
            }
            bck->fd = p;
            fwd->bk = p;

            set_head(p, size | PREV_INUSE);
            set_foot(p, size);

            check_free_chunk(av, p);
        }
```

#### 次のブロックが top chunk の場合: top chunk に統合

```c++
        /*
          If the chunk borders the current high end of memory,
          consolidate into top
        */
        // 解放する chunk の次の chunk が top chunk なら、top chunk に統合する
        else {
            size += nextsize;
            set_head(p, size | PREV_INUSE);
            av->top = p;
            check_chunk(av, p);
        }
```

#### システムへのメモリの返還

```c++
        /*
          If freeing a large space, consolidate possibly-surrounding
          chunks. Then, if the total unused topmost memory exceeds trim
          threshold, ask malloc_trim to reduce top.

          Unless max_fast is 0, we don't know if there are fastbins
          bordering top, so we cannot tell for sure whether threshold
          has been reached unless fastbins are consolidated.  But we
          don't want to consolidate on each free.  As a compromise,
          consolidation is performed if FASTBIN_CONSOLIDATION_THRESHOLD
          is reached.
        */
         // 統合後の chunk のサイズが FASTBIN_CONSOLIDATION_THRESHOLD 以上の場合
         // top chunk に統合した場合は、通常この部分のコードが実行される。
         // システムにメモリを返還する
        if ((unsigned long) (size) >= FASTBIN_CONSOLIDATION_THRESHOLD) {
            // fast chunk があれば統合する
            if (have_fastchunks(av)) malloc_consolidate(av);
            // メイン arena
            if (av == &main_arena) {
#ifndef MORECORE_CANNOT_TRIM
                // top chunk が現在の縮小しきい値以上の場合
                if ((unsigned long) (chunksize(av->top)) >=
                    (unsigned long) (mp_.trim_threshold))
                    systrim(mp_.top_pad, av);
#endif      // メインでない arena なら、直接 heap を縮小する
            } else {
                /* Always try heap_trim(), even if the top chunk is not
                   large, because the corresponding heap might go away.  */
                heap_info *heap = heap_for_ptr(top(av));

                assert(heap->ar_ptr == av);
                heap_trim(heap, mp_.top_pad);
            }
        }

        if (!have_lock) {
            assert(locked);
            __libc_lock_unlock(av->mutex);
        }
```

### mmap された chunk の解放

```c++
    } else {
        //  If the chunk was allocated via mmap, release via munmap().
        munmap_chunk(p);
    }
```

## systrim

## heap_trim

## munmap_chunk
