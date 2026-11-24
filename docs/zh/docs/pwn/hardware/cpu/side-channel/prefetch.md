# prefetch side-channel attack

Prefetch サイドチャネル攻撃(Prefetch Side-channel Attacks)は、[Daniel Gruss](https://gruss.cc/) が論文 _[Prefetch Side-Channel Attacks: Bypassing SMAP and Kernel ASLR](https://gruss.cc/files/prefetch.pdf)_ で提案した補助的な攻撃手法です。この攻撃手法は、Intel CPU の `prefetch` 系命令のハードウェア設計上の弱点を利用し、異なる仮想アドレスで `prefetch` 命令を実行したときの時間差を比較することで、メモリに関する情報をリークさせ、KASLR などの保護を回避します。

CPU の高速な動作は、_投機的実行_(speculative execution。条件分岐の判定の前に後続の分岐を推測し、対応する命令を実行すること)に大きく依存しています。データのプリフェッチ(data prefetching)はこの考え方に基づき、データを投機的にキャッシュへロードするもので、ハードウェア(一時的実行)またはソフトウェア(命令。ただし CPU に無視されることもあります)で行えます。Intel CPU には、プリフェッチ用の命令が 5 つあります。`prefetch0`、`prefetch1`、`prefetch2`、`prefetchchnta`、`prefetchw` で、あるメモリがこれからアクセスされる可能性があることを CPU に能動的に伝えるために使います。ARMv8-A CPUs も、同様のプリフェッチ命令 `PRFM` をサポートしています。

## 攻撃プリミティブの構築

Prefetch サイドチャネル攻撃は、`prefetch` 命令の次の 2 つの特性を利用します。

- **Property 1**: prefetch 命令の実行時間は、CPU 内部の複数のキャッシュの状態に依存する
- **Property 2**: prefetch 命令はいかなる権限チェックも必要としない

### Translation-level oracle

> 作成中です。

###  Address-translation oracle

prefetch 命令はいかなる権限チェックも必要としないため、攻撃者は任意の仮想アドレスで `prefetch` 命令を実行できます。**マップされていないアドレスやカーネルアドレスも含まれます**。これにより、次の手順で 2 つの仮想アドレス $p$ と $\overline{p}$ が同じ物理アドレスにマップされているかを検証できます。

1. アドレス $p$ をフラッシュ(キャッシュから除去)する

2. (アクセスできない)アドレス $\overline{p}$ をプリフェッチする

3. アドレス $p$ を再びロードする

2 つの仮想アドレスが同じ物理アドレスにマップされている場合、手順 2 でアドレス $\overline{p}$ に対して実行した prefetch 命令により、手順 3 でキャッシュヒット(cache hit)が起きる確率が高くなります。この場合、手順 3 の実行時間は、キャッシュミス(cache miss)の場合よりはるかに短くなります。

同様に、prefetch 命令の実行時間(property 1)に基づいて、**対象アドレス p がキャッシュに存在するか**を知ることができます。

1. アドレス $p$ をフラッシュする。

2. 関数またはシステムコールを実行する。

3. アドレス $p$ をプリフェッチする。

手順 2 でアクセスされたアドレス $\overline{p}$ とアドレス $p$ が同じ物理ページにマップされている場合、手順 3 の実行時間はキャッシュミスの場合よりはるかに短くなります。これにより、2 つの仮想アドレス $p$ と $\overline{p}$ が同じ物理アドレスにマップされているかが分かります。ただし、この場合、攻撃者は $\overline{p}$ を知ることはできず、$p$ が関数またはシステムコールで使われたことだけが分かります。

## Translation-level Recovery Attack

> 作成中です。

## Address-Translation Attack

現代のオペレーティングシステムのカーネルには、通常、物理メモリ空間の完全なリニアマッピングがあります。そのため、攻撃者は `Address-translation oracle` を使って、ユーザーアドレス空間のアドレス $p$ に対応する、カーネルアドレス空間内のその領域のアドレス $\overline{p}$ を総当たりで探し、property 1 を利用して前方へ総当たりすることで、カーネルアドレス空間内の、物理アドレス空間へのリニアマッピングの仮想アドレス空間のベースアドレスを取得できます(Linux の場合、この領域の開始アドレスは `page_offset_base` です)。物理アドレスのリニアマッピング領域の開始アドレスより前の仮想アドレスには、対応する物理ページへのマッピングが存在しないため、prefetch 命令の実行時間の差を観察できます。

## KASLR bypass

`Address-translation oracle` の変種を使って KASLR を回避します。同じ物理ページにマップされる仮想アドレスを探す代わりに、次の方法で、ある仮想アドレス $p$ がシステムコールで使われているかを確認します。

1. すべてのキャッシュをフラッシュする(十分に大きな buffer にアクセスして行う)。

2. システムコールを実行する。このとき、対応するページがキャッシュにロードされる。

3. 一連の prefetch 命令の実行時間を測定して、仮想アドレス $p$ がシステムコールで使われているかを知る。

この方法で、対応するシステムコールの仮想アドレスを知ることができ、KASLR を回避できます。

### KASLR bypass with KPTI enabled

KPTI が有効な場合、ユーザーモードのプログラムが使うページテーブルには、カーネルメモリへのマッピングがほとんどありません。しかし、**システムコールのエントリ関数へのマッピングは依然として存在し、これが prefetch サイドチャネル攻撃に隙を残します**。システムコールのエントリ関数もカーネルのコードセグメント内にあるため、prefetch サイドチャネル攻撃を利用して、システムコールのエントリ関数がマップされている仮想アドレスを取得し、KASLR を回避できます。

> [EntryBleed: Breaking KASLR under KPTI with Prefetch (CVE-2022-4543)](https://www.willsroot.io/2022/12/entrybleed.html) を参照してください。

## 例題:TCTF2021 Final - kbrop

> 作成中です。

## REFERENCE

[Prefetch Side-Channel Attacks: Bypassing SMAP and Kernel ASLR](https://gruss.cc/files/prefetch.pdf)

[EntryBleed: Breaking KASLR under KPTI with Prefetch (CVE-2022-4543)](https://www.willsroot.io/2022/12/entrybleed.html)