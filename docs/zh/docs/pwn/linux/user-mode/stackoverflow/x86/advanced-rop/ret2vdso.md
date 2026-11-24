# ret2VDSO

## VDSO の紹介

VDSO(Virtual Dynamically-linked Shared Object)とは何でしょうか。名前からすると「仮想動的リンク共有オブジェクト」といったところで、仮想メモリと同様に、コンピュータ上に実体としては存在しないものです。具体的には、カーネル空間の呼び出しをユーザーのアドレス空間にマップするライブラリです。なぜこれが存在するのでしょうか。一部のシステムコールはユーザーによって頻繁に使われるため、ユーザーモードとカーネルモードの切り替えに大きなオーバーヘッドが生じます。vdso を使うとこのオーバーヘッドを大幅に減らせますし、経路もより良いものになります。ここでいう経路が良いとは、従来の int 0x80 でシステムコールを行う必要がなくなるということです。プロセッサごとに異なる高速システムコール命令が実装されています。

- intel は sysenter、sysexit を実装しています
- amd は syscall、sysret を実装しています

プロセッサのアーキテクチャごとに異なる命令が実装されていると、当然互換性の問題が生じます。そのため Linux は vsyscall インターフェースを実装し、内部で具体的なアーキテクチャに応じた処理を行っています。そして vsyscall は vdso の中に実装されています。

ここで、ついでに vdso を見てみましょう。Linux(kernel 2.6 以降)で ldd /bin/sh を実行すると、linux-vdso.so.1(古いバージョンでは linux-gate.so.1)という名前の動的ファイルが見つかりますが、システム上にはそのようなファイルは存在しません。これが VDSO です。例:

```shell
➜  ~ ldd /bin/sh
	linux-vdso.so.1 =>  (0x00007ffd8ebf2000)
	libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f84ff2f9000)
	/lib64/ld-linux-x86-64.so.2 (0x0000560cae6eb000)
```

高速システムコールのほかに、glibc も VDSO をサポートしており、open()、read()、write()、gettimeofday() は VDSO 内の実装を直接使えます。これによりこれらの呼び出しが高速になります。また、カーネルの新機能も glibc に影響を与えることなくより素早く展開できます。

ここでは intel のプロセッサを例に、簡単に説明します。

sysenter の引数の渡し方は int 0x80 と同じですが、自分で function prolog(32 ビットの場合)を用意する必要があるかもしれません。

```asm
push ebp
mov ebp,esp
```

また、function prolog を用意しない場合は、スタックの位置を変えるために、stack pivot(栈迁移)ができる gadget も必要になります。

## 原理

追記予定です。

## 問題

- **Defcon 2015 Qualifier fuckup**

## 参考

- http://man7.org/linux/man-pages/man7/vdso.7.html
- http://adam8157.info/blog/2011/10/linux-vdso/
