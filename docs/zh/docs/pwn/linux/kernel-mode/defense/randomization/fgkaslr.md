# FGKASLR

## はじめに

KASLR の不足を踏まえて、FGKASLR を実装した研究者がいます。FGKASLR は、KASLR によるベースアドレスのランダム化に加えて、ロード時に関数単位でカーネルコードを並べ替えます。

## 実装

FGKASLR の実装は比較的単純で、主に 2 つの部分に変更が加えられています。現在、FGKASLR は x86_64 アーキテクチャのみをサポートしています。

### コンパイル段階

FGKASLR は gcc のコンパイルオプション `-ffunction-sections` を利用して、カーネル内の各関数を別々の section に配置します。コンパイルの過程で、C 言語で書かれた関数と、特殊な入力セクションに属さない関数は、それぞれ独立した 1 つのセクションになります。アセンブリで書かれたコードは 1 つにまとめたセクションに置かれます。

コンパイル後の vmlinux には、すべてのセクションヘッダ(Section Headers)が残されており、各関数のアドレス範囲が分かるようになっています。さらに、FGKASLR にはリロケーションアドレスの拡張テーブルもあります。この 2 組の情報により、カーネルは展開後に関数を並べ替えられます。

最終的なバイナリの最初のセグメントには、結合されたセクション(複数の関数を結合したもの)と、それぞれ独立したセクションを成す複数の関数が含まれます。

### ロード段階

カーネルの展開後、まず残されたシンボル情報を調べ、ランダム化が必要な `.text.*` セクションを探します。このうち、最初に結合されたセクション(`.text`)はスキップされ、ランダム化されません。後続のセクションのアドレスはランダム化されますが、`.text` セクションとは隣り合ったままです。また、FGKASLR は、リロケーションアドレスを更新する既存のコードを変更し、ロードアドレスに対するオフセットだけでなく、関数セクションの移動先の位置も考慮するようにしています。

新しいメモリレイアウトを隠すため、/proc/kallsyms のシンボルはランダムな順序で並べられます。v4 より前のバージョンでは、このファイルのシンボルはアルファベット順に並んでいました。

コードを解析すると、`layout_randomized_image` 関数の中で、最終的にランダム化されるセクションが計算され、sections に格納されていることが分かります。

```c
	/*
	 * now we need to walk through the section headers and collect the
	 * sizes of the .text sections to be randomized.
	 */
	for (i = 0; i < shnum; i++) {
		s = &sechdrs[i];
		sname = secstrings + s->sh_name;

		if (s->sh_type == SHT_SYMTAB) {
			/* only one symtab per image */
			if (symtab)
				error("Unexpected duplicate symtab");

			symtab = malloc(s->sh_size);
			if (!symtab)
				error("Failed to allocate space for symtab");

			memcpy(symtab, output + s->sh_offset, s->sh_size);
			num_syms = s->sh_size / sizeof(*symtab);
			continue;
		}

		if (s->sh_type == SHT_STRTAB && i != ehdr->e_shstrndx) {
			if (strtab)
				error("Unexpected duplicate strtab");

			strtab = malloc(s->sh_size);
			if (!strtab)
				error("Failed to allocate space for strtab");

			memcpy(strtab, output + s->sh_offset, s->sh_size);
		}

		if (!strcmp(sname, ".text")) {
			if (text)
				error("Unexpected duplicate .text section");

			text = s;
			continue;
		}

		if (!strcmp(sname, ".data..percpu")) {
			/* get start addr for later */
			percpu = s;
			continue;
		}

		if (!(s->sh_flags & SHF_ALLOC) ||
		    !(s->sh_flags & SHF_EXECINSTR) ||
		    !(strstarts(sname, ".text")))
			continue;

		sections[num_sections] = s;

		num_sections++;
	}
	sections[num_sections] = NULL;
	sections_size = num_sections;
```

以下の条件をすべて満たすセクションだけがランダム化の対象になります。

- セクション名が .text で始まる
- section flags に `SHF_ALLOC` が含まれる
- section flags に `SHF_EXECINSTR` が含まれる

したがって、次のコマンドから、次のことが分かります。

- __ksymtab はランダム化の対象にならない
- .data はランダム化の対象にならない

```
> readelf --section-headers -W vmlinux| grep -vE " .text|AX"
...
  [36106] .rodata           PROGBITS        ffffffff81c00000 e1e000 382241 00  WA  0   0 4096
  [36107] .pci_fixup        PROGBITS        ffffffff81f82250 11a0250 002ed0 00   A  0   0 16
  [36108] .tracedata        PROGBITS        ffffffff81f85120 11a3120 000078 00   A  0   0  1
  [36109] __ksymtab         PROGBITS        ffffffff81f85198 11a3198 00b424 00   A  0   0  4
  [36110] __ksymtab_gpl     PROGBITS        ffffffff81f905bc 11ae5bc 00dab8 00   A  0   0  4
  [36111] __ksymtab_strings PROGBITS        ffffffff81f9e074 11bc074 027a82 01 AMS  0   0  1
  [36112] __init_rodata     PROGBITS        ffffffff81fc5b00 11e3b00 000230 00   A  0   0 32
  [36113] __param           PROGBITS        ffffffff81fc5d30 11e3d30 002990 00   A  0   0  8
  [36114] __modver          PROGBITS        ffffffff81fc86c0 11e66c0 000078 00   A  0   0  8
  [36115] __ex_table        PROGBITS        ffffffff81fc8740 11e6738 001c50 00   A  0   0  4
  [36116] .notes            NOTE            ffffffff81fca390 11e8388 0001ec 00   A  0   0  4
  [36117] .data             PROGBITS        ffffffff82000000 11ea000 215d80 00  WA  0   0 8192
  [36118] __bug_table       PROGBITS        ffffffff82215d80 13ffd80 01134c 00  WA  0   0  1
  [36119] .vvar             PROGBITS        ffffffff82228000 14110d0 001000 00  WA  0   0 16
  [36120] .data..percpu     PROGBITS        0000000000000000 1413000 02e000 00  WA  0   0 4096
  [36122] .rela.init.text   RELA            0000000000000000 149eec0 000180 18   I 36137 36121  8
  [36124] .init.data        PROGBITS        ffffffff822b6000 14a0000 18d1a0 00  WA  0   0 8192
  [36125] .x86_cpu_dev.init PROGBITS        ffffffff824431a0 162d1a0 000028 00   A  0   0  8
  [36126] .parainstructions PROGBITS        ffffffff824431c8 162d1c8 01e04c 00   A  0   0  8
  [36127] .altinstructions  PROGBITS        ffffffff82461218 164b214 003a9a 00   A  0   0  1
  [36129] .iommu_table      PROGBITS        ffffffff82465bb0 164fbb0 0000a0 00   A  0   0  8
  [36130] .apicdrivers      PROGBITS        ffffffff82465c50 164fc50 000038 00  WA  0   0  8
  [36132] .smp_locks        PROGBITS        ffffffff82468000 1651610 007000 00   A  0   0  4
  [36133] .data_nosave      PROGBITS        ffffffff8246f000 1658610 001000 00  WA  0   0  4
  [36134] .bss              NOBITS          ffffffff82470000 165a000 590000 00  WA  0   0 4096
  [36135] .brk              NOBITS          ffffffff82a00000 1659610 02c000 00  WA  0   0  1
  [36136] .init.scratch     PROGBITS        ffffffff82c00000 1659620 400000 00  WA  0   0 32
  [36137] .symtab           SYMTAB          0000000000000000 1a59620 30abd8 18     36138 111196  8
  [36138] .strtab           STRTAB          0000000000000000 1d641f8 219a29 00      0   0  1
  [36139] .shstrtab         STRTAB          0000000000000000 1f7dc21 0ed17b 00      0   0  1
Key to Flags:
  W (write), A (alloc), X (execute), M (merge), S (strings), I (info),
  L (link order), O (extra OS processing required), G (group), T (TLS),
  C (compressed), x (unknown), o (OS specific), E (exclude),
  l (large), p (processor specific)
```

## 性能オーバーヘッド

FGKASLR が性能に与える影響は、主に起動と実行の 2 つの段階で生じます。

### 起動段階

起動段階では、FGKASLR は次のことを行います。

- カーネルの ELF ファイルを解析して、ランダム化が必要なセクションを取得する必要がある。
- 乱数生成器を呼び出して、各セクションを格納するアドレスを決定し、配置する。
- メモリ破壊を避けるため、展開済みのカーネルを別の場所にコピーする。
- カーネルがリロケーションする必要のある回数が増える。
- リロケーションが必要な各アドレスがランダム化されたセクション内にあるかを確認する必要があり、該当する場合は新しいオフセットに調整する必要がある。
- アドレス順に並んでいる必要のあるデータテーブルを並べ替える。

最新のシステムでテスト用の VM を起動すると、約 1 秒かかりました。

### 実行段階

実行段階のオーバーヘッドは、実際には具体的な負荷に大きく依存します。ただし、もともと隣り合っていた関数がランダム化によって別々のアドレスに置かれる可能性があるため、相対的に見て全体の性能は低下するはずです。

## メモリオーバーヘッド

起動段階では、FGKASLR は多くのヒープメモリを必要とします。そのため、FGKASLR はメモリの小さいシステムには適さないかもしれません。このメモリはカーネルの展開後に解放されます。

## プログラムサイズへの影響

FGKASLR は追加のセクションヘッダ情報を導入するため、vmlinux ファイルのサイズが増えます。標準的な構成では、vmlinux のサイズは 3% 増加します。圧縮後のイメージサイズは約 15% 増加します。

## 有効化と無効化

### 有効化

カーネルの FGKASLR を有効にするには、`CONFIG_FG_KASLR=y` オプションを有効にする必要があります。

FGKASLR はモジュールのランダム化もサポートしています。FGKASLR が対応するのは x86_64 アーキテクチャのカーネルだけですが、この機能は他のアーキテクチャのモジュールにも対応できます。`CONFIG_MODULE_FG_KASLR=y` でこの機能を有効にできます。

### 無効化

コマンドラインで `nokaslr` を使って KASLR を無効にすると、FGKASLR も同時に無効になります。もちろん、`nofgkaslr` を単独で使って FGKASLR だけを無効にすることもできます。

## 欠点

FGKASLR の特徴から、次のような欠陥があることが分かります。

- 関数単位のランダム化なので、関数内のあるアドレスが分かれば、関数内部の相対アドレスも分かってしまう。
- `.text` セクションは関数のランダム化の対象にならない。そのため、その中の 1 つのアドレスが分かれば、このセクションのすべてのアドレスを取得できる。興味深いことに、システムコールのエントリコードはすべてこのセクション内にある。これは主に、それらのコードがすべてアセンブリコードだからである。さらに、このセクションには次のような有用な gadget がある
    - swapgs_restore_regs_and_return_to_usermode。この部分のコードは KPTI 保護の回避に使える
    - memcpy によるメモリコピー
    - sync_regs。RAX を RDI に入れられる
- `__ksymtab` のカーネルイメージに対するオフセットは固定である。したがって、データをリークできれば、prepare_kernel_cred や commit_creds といった他のシンボルのアドレスをリークできる。具体的な方法は次のとおり
    - カーネルイメージのアドレスから __ksymtab のアドレスを取得する
    - __ksymtab から、対応するシンボルのエントリのアドレスを取得する
    - シンボルのエントリの具体的な内容から、対応するシンボルのアドレスを取得する
- data セクションのカーネルイメージに対するオフセットも固定である。したがって、カーネルイメージのベースアドレスを取得すれば、データ領域のデータのアドレスを計算できる。このセクションには、特に注目すべきデータがいくつかある
    - modprobe_path

### __ksymtab の形式

__ksymtab の各エントリの名前の形式は ` __ksymtab_func_name` です。`prepare_kernel_cred` を例にすると、対応するエントリの名前は ` __ksymtab_prepare_kernel_cred` になります。したがって、この名前を使って、次のように IDA 上で対応する位置を直接見つけられます。

```assembly
__ksymtab:FFFFFFFF81F8D4FC __ksymtab_prepare_kernel_cred dd 0FF5392F4h
__ksymtab:FFFFFFFF81F8D500                 dd 134B2h
__ksymtab:FFFFFFFF81F8D504                 dd 1783Eh
```

`__ksymtab` の各項目の構造は次のとおりです。

```c
struct kernel_symbol {
	int value_offset;
	int name_offset;
	int namespace_offset;
};
```

最初の項目には、現在のアドレスからのリロケーション項目のオフセットが記録されています。したがって、`prepare_kernel_cred` のアドレスは `0xFFFFFFFF81F8D4FC-(2**32-0xFF5392F4)=0xffffffff814c67f0` となるはずです。実際、そのとおりになっています。

```assembly
.text.prepare_kernel_cred:FFFFFFFF814C67F0                 public prepare_kernel_cred
.text.prepare_kernel_cred:FFFFFFFF814C67F0 prepare_kernel_cred proc near           ; CODE XREF: sub_FFFFFFFF814A5ED5+52↑p
```

## 参考文献

- https://lwn.net/Articles/832434/
- https://github.com/kaccardi/linux/compare/fg-kaslr
- https://elixir.bootlin.com/linux/latest/source/include/linux/export.h#L60
- https://www.youtube.com/watch?v=VcqhJKfOcx4
- https://www.phoronix.com/scan.php?page=article&item=kaslr-fgkaslr-benchmark&num=1
