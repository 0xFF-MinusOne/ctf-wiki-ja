# Misc

## __ro_after_init

## 概要

Linux カーネルのデータの多くは `__init` フェーズでのみ初期化され、その後は変更されません。`__ro_after_init` でマークされたメモリは、init フェーズの終了後は再び変更できなくなります。

## 攻撃

`set_memory_rw(unsigned long addr, int numpages)` を使うと、対応するページの権限を変更できます。

## mmap_min_addr

mmap_min_addr は NULL Pointer Dereference への対策で、ユーザープロセスが mmap で使用できる最小の仮想メモリアドレスを指定します。

## 参考文献

- https://lwn.net/Articles/676145/
- https://lwn.net/Articles/666550/
- https://lore.kernel.org/patchwork/patch/621386/