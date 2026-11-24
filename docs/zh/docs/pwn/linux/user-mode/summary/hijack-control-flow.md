# プログラムの実行フローの制御

プログラムの実行フローを制御するには、次のような方法が考えられます。

## EIP を直接制御する



## リターンアドレス

スタック上のリターンアドレスを制御します。

## ジャンプポインタ

ここでは次のような方法が考えられます。

- call
- jmp

## 関数ポインタ

一般的な関数ポインタには次のものがあります。

- vtable、function table。たとえば IO_FILE の vtable、printf function table。
- hook ポインタ。たとえば `malloc_hook`、`free_hook`。
- handler

## 制御フローに関係する変数を変更する
