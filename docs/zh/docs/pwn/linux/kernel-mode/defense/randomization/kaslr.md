# KASLR

## 概要

KASLR が有効なカーネルでは、カーネルのコードセグメントのベースアドレスなどのアドレスが全体的にずれます。

## 発展の歴史

TODO。

## 実装

TODO。

## 有効化と無効化

qemu で起動したカーネルの場合は、`-append` オプションに `kaslr` を追加すると KASLR を有効にできます。

qemu で起動したカーネルの場合は、`-append` オプションに `nokaslr` を追加すると KASLR を無効にできます。

## Attack

カーネルのあるセグメントのアドレスをリークさせれば、そのセグメント内のすべてのアドレスが分かります。たとえば、カーネルのコードセグメントのアドレスをリークさせれば、カーネルのコードセグメントのすべてのアドレスが分かります。

## 参考文献

- https://outflux.net/slides/2013/lss/kaslr.pdf
- https://bneuburg.github.io/volatility/kaslr/2017/04/26/KASLR1.html

