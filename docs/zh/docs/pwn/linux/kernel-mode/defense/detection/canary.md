# Kernel Stack Canary

Canary は典型的な検知機構です。Linux カーネルにおける Canary の実装はアーキテクチャに依存するため、ここではアーキテクチャごとに紹介します。

## x86

### 概要

x86 アーキテクチャでは、同一の task 内では同じ Canary が使われます。

### 発展の歴史

TODO。

### 実装

TODO。

### 使い方

#### 有効化

カーネルのコンパイル時に CONFIG_CC_STACKPROTECTOR オプションを設定すると、この保護を有効にできます。

#### 無効化

Canary 保護を無効にするには、コンパイルオプションを無効にしてカーネルを再コンパイルする必要があります。

### 状態の確認

次の方法で、Canary 保護が有効かどうかを確認できます。

1. `checksec` 
2. バイナリを手作業で解析し、関数内に Canary を保存・チェックするコードがあるかを見る

### 特徴

x86 アーキテクチャにおける Canary 実装の特徴は、同一の task が Canary を共有することです。

### 攻撃

x86 アーキテクチャにおける Canary 実装のこの特徴から、あるシステムコール中の Canary を一度リークさせれば、同じ task の他のシステムコール中の Canary もすべてリークしたことになります。

## 参考文献

- https://www.workofard.com/2018/01/per-task-stack-canaries-for-arm64/
- [PESC: A Per System-Call Stack Canary Design for Linux Kernel](https://yajin.org/papers/pesc.pdf)
