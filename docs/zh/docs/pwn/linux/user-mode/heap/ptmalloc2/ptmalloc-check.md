# ヒープのチェック

## _int_malloc

## 初期チェック

| チェック対象  |                   チェック条件                   |         情報          |
| :---: | :--------------------------------------: | :-----------------: |
| 要求サイズ | REQUEST_OUT_OF_RANGE(req) ：((unsigned long) (req) >= (unsigned long) (INTERNAL_SIZE_T)(-2 * MINSIZE)) | __set_errno(ENOMEM) |

### fastbin

| チェック対象     |                  チェック条件                   |                エラーメッセージ                |
| -------- | :-------------------------------------: | :--------------------------------: |
| チャンクのサイズ | fastbin_index(chunksize(victim)) != idx | malloc(): memory corruption (fast) |

### Unsorted bin

|         チェック対象          |                   チェック条件                   |            エラーメッセージ             |
| :-------------------: | :--------------------------------------: | :-------------------------: |
| unsorted bin のチャンクのサイズ | chunksize_nomask (victim) <= 2 * SIZE_SZ \|\| chunksize_nomask (victim)  av->system_mem | malloc(): memory corruption |



### top chunk

|      チェック対象      |                   チェック条件                   |  情報  |
| :------------: | :--------------------------------------: | :--: |
| top chunk のサイズ | (unsigned long) (size) >= (unsigned long) (nb + MINSIZE) | 満たせば進入可 |



## __libc_free

### mmap されたチャンク

|      チェック対象      |         チェック条件         |  情報  |
| :------------: | :------------------: | :--: |
| チャンクの size のフラグビット | chunk_is_mmapped (p) | 満たせば進入可 |

### mmap されていないチャンク

## __int_free

### 初期チェック

|    チェック対象    |                   チェック条件                   |          エラーメッセージ           |
| :--------: | :--------------------------------------: | :---------------------: |
| 解放するチャンクの位置  | (uintptr_t) p > (uintptr_t) -size \|\| misaligned_chunk(p) | free(): invalid pointer |
| 解放するチャンクのサイズ |  size < MINSIZE \|\| !aligned_OK(size)   |  free(): invalid size   |

### fastbin

|         チェック対象          |                   チェック条件                   |                エラーメッセージ                 |
| :-------------------: | :--------------------------------------: | :---------------------------------: |
|  解放するチャンクの次のチャンクのサイズ   | chunksize_nomask(chunk_at_offset(p, size)) <= 2 * SIZE_SZ， chunksize(chunk_at_offset(p, size)) >= av->system_mem |  free(): invalid next size (fast)   |
| 解放するチャンクに対応するリストの先頭のチャンク | fb = &fastbin(av, idx)，old= *fb， old == p | double free or corruption (fasttop) |
|       fastbin のインデックス       |      old != NULL && old_idx != idx       |    invalid fastbin entry (free)     |

### mmap されていないチャンクのチェック

|     チェック対象      |                   チェック条件                   |                エラーメッセージ                |
| :-----------: | :--------------------------------------: | :--------------------------------: |
|   解放するチャンクの位置   |               p == av->top               |  double free or corruption (top)   |
| 次のチャンクの位置 | contiguous (av) && (char *) nextchunk  >= ((char *) av->top + chunksize(av->top)) |  double free or corruption (out)   |
| 次のチャンクのサイズ | chunksize_nomask (nextchunk) <= 2 * SIZE_SZ \|\|  nextsize >= av->system_mem | free(): invalid next size (normal) |

## unlink

|         チェック対象          |                   チェック条件                   |                   エラーメッセージ                   |
| :-------------------: | :--------------------------------------: | :--------------------------------------: |
| size **vs** prev_size | chunksize(P) != prev_size (next_chunk(P)) |       corrupted size vs. prev_size       |
|     fd, bk の双方向リストのチェック     |       FD->bk != P \|\| BK->fd != P       |       corrupted double-linked list       |
|     nextsize の双方向リスト     | P->fd_nextsize->bk_nextsize != P \|\| P->bk_nextsize->fd_nextsize != P | corrupted double-linked list (not small) |
