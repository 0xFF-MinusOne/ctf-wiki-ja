# 情報漏えい

## dmesg_restrict

カーネルログにはアドレス情報や機微な情報が含まれる可能性があるため、研究者はカーネルログへのアクセスを制限する必要があると提案しました。

このオプションは、`dmesg` でカーネルログを閲覧できるかどうかを制御します。`dmesg_restrict` が 0 のときは制限がありません。1 のときは、`CAP_SYSLOG` 権限を持つユーザーだけが `dmesg` コマンドでカーネルログを閲覧できます。

```
dmesg_restrict:

This toggle indicates whether unprivileged users are prevented
from using dmesg(8) to view messages from the kernel's log buffer.
When dmesg_restrict is set to (0) there are no restrictions. When
dmesg_restrict is set set to (1), users must have CAP_SYSLOG to use
dmesg(8).

The kernel config option CONFIG_SECURITY_DMESG_RESTRICT sets the
default value of dmesg_restrict.
```

## kptr_restrict

このオプションは、カーネルアドレスを出力する際に課す制限を制御します。主に次のインターフェースが制限の対象です。

- /proc 経由で取得できるカーネルアドレス
- その他のインターフェース経由で取得できるアドレス(要調査)

具体的な出力内容は、このオプションに設定した値によって変わります。

- 0:デフォルトで、制限はありません。
- 1:`％pK` で出力されるカーネルポインタのアドレスは、ユーザーが CAP_SYSLOG 権限を持ち、かつ group id が real id と等しい場合を除き、0 に置き換えられます。
- 2:`％pK` で出力されるカーネルポインタはすべて 0 に置き換えられます。つまり、権限とは無関係です。

```
kptr_restrict:

This toggle indicates whether restrictions are placed on
exposing kernel addresses via /proc and other interfaces.

When kptr_restrict is set to 0 (the default) the address is hashed before
printing. (This is the equivalent to %p.)

When kptr_restrict is set to (1), kernel pointers printed using the %pK
format specifier will be replaced with 0's unless the user has CAP_SYSLOG
and effective user and group ids are equal to the real ids. This is
because %pK checks are done at read() time rather than open() time, so
if permissions are elevated between the open() and the read() (e.g via
a setuid binary) then %pK will not leak kernel pointers to unprivileged
users. Note, this is a temporary solution only. The correct long-term
solution is to do the permission checks at open() time. Consider removing
world read permissions from files that use %pK, and using dmesg_restrict
to protect against uses of %pK in dmesg(8) if leaking kernel pointer
values to unprivileged users is a concern.

When kptr_restrict is set to (2), kernel pointers printed using
%pK will be replaced with 0's regardless of privileges.
```

この保護が有効になると、攻撃者は `/proc/kallsyms` から、commit_creds や prepare_kernel_cred といったカーネル内の機微なアドレスを取得できなくなります。

## 参考文献

- https://blog.csdn.net/gatieme/article/details/78311841
