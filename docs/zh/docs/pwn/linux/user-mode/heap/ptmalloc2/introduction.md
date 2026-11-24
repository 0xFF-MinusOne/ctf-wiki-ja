# ヒープの悪用

この章では、次の順序で説明します。

1. 私たちがよく知っている、動的メモリ確保を行うヒープのマクロな操作を説明する
2. これらの操作を実現するために使われるデータ構造を説明する
3. これらのデータ構造を使ってヒープの確保と回収を実現する具体的な操作を説明する
4. ヒープのさまざまな悪用テクニックを、易しいものから難しいものへと順に説明する

アプリケーションごとにメモリの要求などの特性が異なるため、現在のヒープの実装にはさまざまな種類があります。具体的には次のとおりです。

```text
dlmalloc  – General purpose allocator
ptmalloc2 – glibc
jemalloc  – FreeBSD and Firefox
tcmalloc  – Google
libumem   – Solaris
```

ここでは主に glibc のヒープの実装を中心に説明します。今後時間があれば、ほかのヒープの実装とその悪用についても引き続き説明します。

この部分で主に参考にした資料は次のとおりです。本文には参考資料と同じ内容が多く含まれますが、以降は逐一断りません。

- [black hat heap exploitation](https://www.blackhat.com/presentations/bh-usa-07/Ferguson/Whitepaper/bh-usa-07-ferguson-WP.pdf)
- [github heap exploition](https://heap-exploitation.dhavalkapil.com/)
- [sploitfun](https://sploitfun.wordpress.com/archives/)
- glibc のソースコード
- そのほかの参考文献は ref ディレクトリのファイルを参照してください
