# Change Others

特権プロセスの実行の流れを変えられれば、権限昇格も実現できます。ここでは、特権プロセスの実行の流れを変える方法を次の観点から考えます。

- データを改ざんする
- コードを改ざんする

## データを改ざんする

ここでは、特権プロセスが使うデータを改ざんして権限昇格する方法をいくつか紹介します。

### シンボリックリンク

root 権限のプロセスがシンボリックリンクのプログラムを実行し、そのシンボリックリンク、またはリンク先のプログラムを攻撃者が制御できる場合、攻撃者は権限昇格を実現できます。

### call_usermodehelper

`call_usermodehelper` は、カーネルスレッドからユーザー空間のアプリケーションを実行する方法で、起動されたプロセスは root 権限を持ちます。したがって、**実行するアプリケーションを制御**できれば、権限昇格を実現できます。カーネルでは、`call_usermodehelper` が実行するアプリケーションは多くの場合ある変数で指定されているため、その変数を書き換える方法を考えればよいことになります。

なお、最近の一部の CTF の問題や少数の実システム(AOSP カーネルなど)では CONFIG_STATIC_USERMODEHELPER オプションが有効になっています。これにより `call_usermodehelper` は特定のアプリケーション(コンパイル時に決まる読み取り専用の文字列で指定されるもの)しか直接実行できなくなり、この攻略手法は防がれます。

これは典型的なデータフロー攻撃の手法です。よく使われる方法は主に次のとおりです。

#### modprobe_path の書き換え

modprobe_path を書き換えて権限昇格する基本的な流れは次のとおりです。

1. modprobe_path のアドレスを取得する。
2. modprobe_path を、指定したプログラムに書き換える。
3. `call_modprobe` を実行させて権限昇格を実現する。実行させるには次のような方法があります。
    1. (すでに古い)不正な実行ファイルを実行する。不正な実行ファイルは、所定の条件を満たす必要があります(call_usermodehelper の節の説明を参照)。ただし、2024 年 11 月に導入された[新しいパッチ](https://web.git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=fa1bdca98d74472dcdb79cb948b54f63b5886c04)により、不正な実行ファイルのロード時に binfmt が自動ロードされなくなったため、この方法は Linux 6.12 以降のバージョンでは使えません。
    2. カーネルに新しいカーネルモジュールをロードさせる(未知のプロトコルを使うなど)ことで実行させる。

modprobe_path を使う場合のテンプレートも示します。

```c
// step 1. modify modprobe_path to the target value

// step 2. create related file
system("echo -ne '#!/bin/sh\n/bin/cp /flag /home/pwn/flag\n/bin/chmod 777 /home/pwn/flag\ncat flag' > /home/pwn/catflag.sh");
system("chmod +x /home/pwn/catflag.sh");

// step 3. trigger modprobe using unknown executable (may be obsolete)
system("echo -ne '\\xff\\xff\\xff\\xff' > /home/pwn/dummy");
system("chmod +x /home/pwn/dummy");
system("/home/pwn/dummy");

// step 3. trigger modprobe using unknown protocol
socket(AF_INET,SOCK_STREAM,132);
```

この過程では、modprobe_path をどのように特定するかが特に重要になります。

##### 直接特定する

modprobe_path の値は決まっているため、メモリをスキャンして対応する文字列を探せます。これには、メモリをスキャンする能力が必要です。

##### 間接的に特定する

modprobe_path のカーネルベースアドレスからのオフセットは固定なので、まずカーネルのベースアドレスを取得し、相対オフセットから modprobe_path のアドレスを求められます。

#### poweroff_cmd の書き換え

1. poweroff_cmd を、指定したプログラムに書き換える。
2. 制御フローを奪って `__orderly_poweroff` を実行させる。

poweroff_cmd の特定方法は、`modprobe_path` の特定と同様の方法が使えます。

#### core_pattern の書き換え

1. core_pattern を `|/path/to/your/program` に書き換える。
2. クラッシュダンプを有効にし、カーネルに core_pattern の[パイプ記号以降のプログラム](https://elixir.bootlin.com/linux/v6.18.1/source/fs/coredump.c#L971)を実行させる。

core_pattern 中の大文字の %P はクラッシュしたプロセスのホスト側での PID を表すため、コンテナ環境での権限昇格では modprobe_path の代わりによく使われます。

core_pattern の特定方法は、`modprobe_path` の特定と同様の方法が使えます。  
core_pattern を使った権限昇格の詳細については、[最近の kctf の exp](https://github.com/google/security-research/blob/master/pocs/linux/kernelctf/CVE-2025-21836_lts/exploit/lts-6.6.75/exploit.c#L398) を参照してください。  

## コードを改ざんする

プログラムの実行中に、root 権限のプロセスが実行するコードを書き換えられるなら、権限昇格を実現できます。

### vDSO のコードの書き換え

カーネルの vDSO のコードは、すべてのユーザー空間プロセスにマップされます。高い権限のプロセスが vDSO 内の関数を定期的に呼び出す場合、vDSO 内の該当関数を特定の shellcode に書き換えることを考えられます。高い権限のプロセスがそのコードを実行したとき、権限昇格が可能になります。

初期の Linux では vDSO は書き込み可能でした。こうしたリスクを考慮して、Kees Cook は `post-init read-only` のデータ、つまり初期化後に書き込まれないデータを読み取り専用にする仕組みを導入し、この種の攻略を防ぎました。

導入前は、vDSO に対応する raw_data にはアラインメント属性が付いているだけでした。

```c
	fprintf(outfile, "/* AUTOMATICALLY GENERATED -- DO NOT EDIT */\n\n");
	fprintf(outfile, "#include <linux/linkage.h>\n");
	fprintf(outfile, "#include <asm/page_types.h>\n");
	fprintf(outfile, "#include <asm/vdso.h>\n");
	fprintf(outfile, "\n");
	fprintf(outfile,
		"static unsigned char raw_data[%lu] __page_aligned_data = {",
		mapping_size);
```

導入後は、vDSO に対応する raw_data は初期化後読み取り専用としてマークされています。

```c
	fprintf(outfile, "/* AUTOMATICALLY GENERATED -- DO NOT EDIT */\n\n");
	fprintf(outfile, "#include <linux/linkage.h>\n");
	fprintf(outfile, "#include <asm/page_types.h>\n");
	fprintf(outfile, "#include <asm/vdso.h>\n");
	fprintf(outfile, "\n");
	fprintf(outfile,
		"static unsigned char raw_data[%lu] __ro_after_init __aligned(PAGE_SIZE) = {",
		mapping_size);
```

vDSO を書き換えて権限昇格する基本的な方法は次のとおりです。

- vDSO を特定する
- vDSO の特定の関数を、指定した shellcode に書き換える
- shellcode が実行されるのを待つ

ここでは、vDSO をどのように特定するかが特に重要になります。

#### ida で特定する

ここでは、vmlinux から vDSO の位置を見つける方法を紹介します。

1. ida で init_vdso 関数のアドレスを特定する

```c
__int64 init_vdso()
{
  init_vdso_image(&vdso_image_64 + 0x20000000);
  init_vdso_image(&vdso_image_x32 + 0x20000000);
  cpu_maps_update_begin();
  on_each_cpu((char *)startup_64 + 0x100003EA0LL, 0LL, 1LL);
  _register_cpu_notifier(&sdata + 536882764);
  cpu_maps_update_done();
  return 0LL;
}
```

2. `vdso_image_64` と `vdso_image_x32` が見つかります。`vdso_image_64` を例に、その変数のアドレスへ移動します

```
.rodata:FFFFFFFF81A01300                 public vdso_image_64
.rodata:FFFFFFFF81A01300 vdso_image_64   dq offset raw_data      ; DATA XREF: arch_setup_additional_pages+18↑o
.rodata:FFFFFFFF81A01300                                         ; init_vdso+1↓o
```

3. `raw_data` をクリックすると、64 ビット vDSO のカーネルイメージ内でのアドレスが分かります。vDSO は確かにページアラインされています。

```
.data:FFFFFFFF81E04000 raw_data        db  7Fh ;              ; DATA XREF: .rodata:vdso_image_64↑o
.data:FFFFFFFF81E04001                 db  45h ; E
.data:FFFFFFFF81E04002                 db  4Ch ; L
.data:FFFFFFFF81E04003                 db  46h ; F
```

最後のシンボルからも分かるように、`raw_data` を直接使って vDSO を探すこともできます。

#### メモリ上で特定する

##### 直接特定する

vDSO は実は ELF ファイルであり、ELF ヘッダを持っています。また、vDSO 内の特定の位置にはエクスポート関数の文字列が格納されています。この 2 つの特徴からメモリをスキャンして、vDSO の位置を特定できます。

##### 間接的に特定する

vDSO のカーネルベースアドレスからのオフセットは固定なので、まずカーネルのベースアドレスを取得し、相対オフセットから vDSO のアドレスを求められます。

#### 参考

- https://lwn.net/Articles/676145/
- https://lwn.net/Articles/666550/
- https://sam4k.com/like-techniques-modprobe_path/
- https://theori.io/blog/reviving-the-modprobe-path-technique-overcoming-search-binary-handler-patch
- https://github.com/google/security-research/blob/master/pocs/linux/kernelctf/CVE-2025-21836_lts/exploit/lts-6.6.75/exploit.c
