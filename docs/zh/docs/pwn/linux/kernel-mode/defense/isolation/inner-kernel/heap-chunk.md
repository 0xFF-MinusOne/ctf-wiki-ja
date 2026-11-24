# 内部隔離

## ヒープチャンクの隔離

### GFP\_KERNEL と GFP\_KERNEL\_ACCOUNT の隔離

`GFP_KERNEL` と `GFP_KERNEL_ACCOUNT` はカーネルで最も一般的で汎用的な確保用フラグで、通常はどちらも同じ `kmem_cache`、つまり汎用の `kmalloc-xx` から確保されます。

5.9 より前のバージョンでは `GFP_KERNEL` と `GFP_KERNEL_ACCOUNT` の間に隔離機構がありましたが、[この commit](https://github.com/torvalds/linux/commit/10befea91b61c4e2c2d1df06a2e978d182fcf792) で隔離機構は廃止されました。その後、カーネルバージョン 5.14 以降では [この commit](https://github.com/torvalds/linux/commit/494c1dfe855ec1f70f89552fce5eadf4a1717552) で再び導入されています。

- `CONFIG_MEMCG_KMEM` コンパイルオプションが有効なカーネル(デフォルトで有効)では、`GFP_KERNEL_ACCOUNT` で確保される汎用オブジェクトのために、**独立した `kmem_cache` の組(名前は `kmalloc-cg-*`)が作られます**。これにより、2 種類のフラグを使うオブジェクト同士が隔離されます。

### SLAB_ACCOUNT

説明によると、`kmem_cache_create` で cache を作成する際に `SLAB_ACCOUNT` フラグを渡すと、その cache は独立して存在し、同じサイズの他の cache と統合されません。

```
Currently, if we want to account all objects of a particular kmem cache,
we have to pass __GFP_ACCOUNT to each kmem_cache_alloc call, which is
inconvenient. This patch introduces SLAB_ACCOUNT flag which if passed to
kmem_cache_create will force accounting for every allocation from this
cache even if __GFP_ACCOUNT is not passed.

This patch does not make any of the existing caches use this flag - it
will be done later in the series.

Note, a cache with SLAB_ACCOUNT cannot be merged with a cache w/o
SLAB_ACCOUNT, i.e. using this flag will probably reduce the number of
merged slabs even if kmem accounting is not used (only compiled in).
```

初期の頃は、多くの構造体(**cred 構造体**など)に対応するヒープチャンクは独立して存在せず、同じサイズのヒープチャンクと同じ cache を使っていました。Linux 4.5 でこのフラグが導入されると、多くの構造体が自前の cache を使うようになりました。ただし、上の説明によれば、この特性はもともとセキュリティのために導入されたものではないようです。

```
Mark those kmem allocations that are known to be easily triggered from
userspace as __GFP_ACCOUNT/SLAB_ACCOUNT, which makes them accounted to
memcg.  For the list, see below:

 - threadinfo
 - task_struct
 - task_delay_info
 - pid
 - cred
 - mm_struct
 - vm_area_struct and vm_region (nommu)
 - anon_vma and anon_vma_chain
 - signal_struct
 - sighand_struct
 - fs_struct
 - files_struct
 - fdtable and fdtable->full_fds_bits
 - dentry and external_name
 - inode for all filesystems. This is the most tedious part, because
   most filesystems overwrite the alloc_inode method.

The list is far from complete, so feel free to add more objects.
Nevertheless, it should be close to "account everything" approach and
keep most workloads within bounds.  Malevolent users will be able to
breach the limit, but this was possible even with the former "account
everything" approach (simply because it did not account everything in
fact).
```

### 参考文献

- https://lore.kernel.org/patchwork/patch/616610/
- https://github.com/torvalds/linux/commit/5d097056c9a017a3b720849efb5432f37acabbac#diff-3cb5667a88a24e8d5abc7042f5c4193698d6b962157f637f9729e61198eec63a
- https://github.com/torvalds/linux/commit/230e9fc2860450fbb1f33bdcf9093d92d7d91f5b#diff-cc9aa90e094e6e0f47bd7300db4f33cf4366b98b55d8753744f31eb69c691016
- https://github.com/torvalds/linux/commit/10befea91b61c4e2c2d1df06a2e978d182fcf792
- https://github.com/torvalds/linux/commit/494c1dfe855ec1f70f89552fce5eadf4a1717552

