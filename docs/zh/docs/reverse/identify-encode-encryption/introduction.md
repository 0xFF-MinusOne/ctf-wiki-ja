# 一般的な暗号アルゴリズムとエンコードの識別

## はじめに

データを変換する過程では、単純なバイト操作のほかに、一般的なエンコードや暗号アルゴリズムが使われることがあります。そのため、対応するエンコードや暗号アルゴリズムをすばやく識別できれば、アルゴリズム全体をより早く解析できます。CTF のリバースエンジニアリングでよく出てくる暗号アルゴリズムには、base64、TEA、AES、RC4、MD5 などがあります。

## Base64

Base64 は、64個の印字可能文字でバイナリデータを表現する方式です。変換するときは、3バイトのデータを順に24ビットのバッファに入れ、先に来たバイトが上位ビットを占めます。データが3バイトに満たない場合は、バッファに残ったビットを0で埋めます。毎回6ビット(![{\displaystyle 2^{6}=64}](https://wikimedia.org/api/rest_v1/media/math/render/svg/c4becc8d811901597b9807eccff60f0897e3701a))ずつ取り出し、その値に従って `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/ ` の中から文字を選んでエンコード後の出力とし、入力データをすべて変換し終えるまで繰り返します。





一般に、Base64 を識別する特徴はインデックステーブルです。`ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/ ` のようなインデックステーブルが見つかれば、簡単な解析を加えるだけで、ほぼ Base64 エンコードだと判定できます。

![](http://ob2hrvcxg.bkt.clouddn.com/20180822140744.png)



もちろん、問題によっては base64 のインデックステーブルが変更されています。base64 の亜種の多くは、このインデックステーブルを変更したものです。





## Tea

[暗号学](https://zh.wikipedia.org/wiki/%E5%AF%86%E7%A0%81%E5%AD%A6)において、**Tiny Encryption Algorithm**(TEA)は、記述や[実行](https://zh.wikipedia.org/w/index.php?title=%E6%89%A7%E8%A1%8C&action=edit&redlink=1)が容易な[ブロック暗号](https://zh.wikipedia.org/wiki/%E5%A1%8A%E5%AF%86%E7%A2%BC)で、通常はごくわずかなコードで実装できます。設計者は[ケンブリッジ大学コンピュータ研究所](https://zh.wikipedia.org/wiki/%E5%89%91%E6%A1%A5%E5%A4%A7%E5%AD%A6)の[デビッド・ホイーラー](https://zh.wikipedia.org/w/index.php?title=%E5%A4%A7%E5%8D%AB%C2%B7%E6%83%A0%E5%8B%92&action=edit&redlink=1)と[ロジャー・ニーダム](https://zh.wikipedia.org/w/index.php?title=%E7%BD%97%E6%9D%B0%C2%B7%E5%B0%BC%E8%BE%BE%E5%A7%86&action=edit&redlink=1)です。



参考コード:

```c
#include <stdint.h>

void encrypt (uint32_t* v, uint32_t* k) {
    uint32_t v0=v[0], v1=v[1], sum=0, i;           /* set up */
    uint32_t delta=0x9e3779b9;                     /* a key schedule constant */
    uint32_t k0=k[0], k1=k[1], k2=k[2], k3=k[3];   /* cache key */
    for (i=0; i < 32; i++) {                       /* basic cycle start */
        sum += delta;
        v0 += ((v1<<4) + k0) ^ (v1 + sum) ^ ((v1>>5) + k1);
        v1 += ((v0<<4) + k2) ^ (v0 + sum) ^ ((v0>>5) + k3);  
    }                                              /* end cycle */
    v[0]=v0; v[1]=v1;
}

void decrypt (uint32_t* v, uint32_t* k) {
    uint32_t v0=v[0], v1=v[1], sum=0xC6EF3720, i;  /* set up */
    uint32_t delta=0x9e3779b9;                     /* a key schedule constant */
    uint32_t k0=k[0], k1=k[1], k2=k[2], k3=k[3];   /* cache key */
    for (i=0; i<32; i++) {                         /* basic cycle start */
        v1 -= ((v0<<4) + k2) ^ (v0 + sum) ^ ((v0>>5) + k3);
        v0 -= ((v1<<4) + k0) ^ (v1 + sum) ^ ((v1>>5) + k1);
        sum -= delta;                                   
    }                                              /* end cycle */
    v[0]=v0; v[1]=v1;
}
```



TEA アルゴリズムを識別する最も主要な特徴は、マジックナンバー 0x9e3779b9 を持つことです。もちろん、TEA アルゴリズムにも改造されたものがあります。興味のある方は 2018 0ctf Quals の milk-tea を見てください。





## RC4

[暗号学](https://zh.wikipedia.org/wiki/%E5%AF%86%E7%A2%BC%E5%AD%B8)において、**RC4**(Rivest Cipher 4 の略)は[ストリーム暗号](https://zh.wikipedia.org/wiki/%E6%B5%81%E5%8A%A0%E5%AF%86)アルゴリズムで、[鍵](https://zh.wikipedia.org/wiki/%E5%AF%86%E9%92%A5)の長さを可変にできます。暗号化と復号に同じ鍵を使うため、[共通鍵暗号](https://zh.wikipedia.org/wiki/%E5%AF%B9%E7%A7%B0%E5%8A%A0%E5%AF%86)アルゴリズムでもあります。RC4 は[WEP](https://zh.wikipedia.org/wiki/%E6%9C%89%E7%B7%9A%E7%AD%89%E6%95%88%E5%8A%A0%E5%AF%86)(Wired Equivalent Privacy)で採用された暗号アルゴリズムで、かつては [TLS](https://zh.wikipedia.org/wiki/%E4%BC%A0%E8%BE%93%E5%B1%82%E5%AE%89%E5%85%A8%E5%8D%8F%E8%AE%AE) で使用できるアルゴリズムの1つでもありました。



```C
void rc4_init(unsigned char *s, unsigned char *key, unsigned long Len) //初期化関数
{
    int i =0, j = 0;
    unsigned char k[256] = {0}; // 符号なし型でなければならない。そうでないと暗号文の一部が誤る
    unsigned char tmp = 0;
    for (i=0;i<256;i++) {
        s[i] = i;
        k[i] = key[i%Len];
    }
    for (i=0; i<256; i++) {
        j=(j+s[i]+k[i])%256;
        tmp = s[i];
        s[i] = s[j]; //s[i] と s[j] を交換
        s[j] = tmp;
    }
 }

void rc4_crypt(unsigned char *s, unsigned char *Data, unsigned long Len) //暗号化・復号
{
    int i = 0, j = 0, t = 0;
    unsigned long k = 0;
    unsigned char tmp;
    for(k=0;k<Len;k++) {
        i=(i+1)%256;
        j=(j+s[i])%256;
        tmp = s[i];
        s[i] = s[j]; //s[x] と s[y] を交換
        s[j] = tmp;
        t=(s[i]+s[j])%256;
        Data[k] ^= s[t];
     }
} 
```

初期化コードを解析すると、文字配列 s に初期値が代入されており、その値が順に増えていることがわかります。そのあと s に対して256回の交換操作が行われます。この初期化コードを見分けることで、RC4 アルゴリズムだとわかります。

擬似コードで表すと次のとおりです。

まず、長さ256の[S-box](https://zh.wikipedia.org/wiki/S%E7%9B%92)を初期化します。最初の for ループで0から255までの重複しない要素を S-box に入れます。2つ目の for ループで、鍵に従って S-box をかき混ぜます。

```c
  for i from 0 to 255
     S[i] := i
 endfor
 j := 0
 for( i=0 ; i<256 ; i++)
     j := (j + S[i] + key[i mod keylength]) % 256
     swap values of S[i] and S[j]
 endfor
```

以下で i と j は2つのポインタです。1バイトを受け取るたびに while ループを実行します。一定のアルゴリズム((a)、(b))で S-box の要素を1つ選び、入力バイトと XOR して k を得ます。ループの中では S-box も変更されます((c))。入力が[平文](https://zh.wikipedia.org/wiki/%E6%98%8E%E6%96%87)なら出力は[暗号文](https://zh.wikipedia.org/wiki/%E5%AF%86%E6%96%87)に、入力が暗号文なら出力は平文になります。

```c
 i := 0
 j := 0
 while GeneratingOutput:
     i := (i + 1) mod 256   //a
     j := (j + S[i]) mod 256 //b
     swap values of S[i] and S[j]  //c
     k := inputByte ^ S[(S[i] + S[j]) % 256]
     output K
 endwhile
```

このアルゴリズムでは、256回のループごとに、S-box の各要素が少なくとも1回は交換されることが保証されます。



### Python 復号スクリプト

対応する例題: 『从 0 到 1』RE 編 - BabyAlgorithm

[問題へのリンク](https://buuoj.cn/challenges#[%E7%AC%AC%E4%BA%94%E7%AB%A0%20CTF%E4%B9%8BRE%E7%AB%A0]BabyAlgorithm)

```python
import base64
def rc4_main(key = "init_key", message = "init_message"):
    print("RC4解密主函数调用成功")
    print('\n')
    s_box = rc4_init_sbox(key)
    crypt = rc4_excrypt(message, s_box)
    return crypt
def rc4_init_sbox(key):
    s_box = list(range(256))
    print("原来的 s 盒：%s" % s_box)
    print('\n')
    j = 0
    for i in range(256):
        j = (j + s_box[i] + ord(key[i % len(key)])) % 256
        s_box[i], s_box[j] = s_box[j], s_box[i]
    print("混乱后的 s 盒：%s"% s_box)
    print('\n')
    return s_box
def rc4_excrypt(plain, box):
    print("调用解密程序成功。")
    print('\n')
    plain = base64.b64decode(plain.encode('utf-8'))
    plain = bytes.decode(plain)
    res = []
    i = j = 0
    for s in plain:
        i = (i + 1) % 256
        j = (j + box[i]) % 256
        box[i], box[j] = box[j], box[i]
        t = (box[i] + box[j]) % 256
        k = box[t]
        res.append(chr(ord(s) ^ k))
    print("res用于解密字符串，解密后是：%res" %res)
    print('\n')
    cipher = "".join(res)
    print("解密后的字符串是：%s" %cipher)
    print('\n')
    print("解密后的输出(没经过任何编码):")
    print('\n')
    return cipher
a=[] #cipher
key=""
s=""
for i in a:
    s+=chr(i)
s=str(base64.b64encode(s.encode('utf-8')), 'utf-8')
rc4_main(key, s)
```

## MD5

**MD5 メッセージダイジェストアルゴリズム**(MD5 Message-Digest Algorithm)は、広く使われている[暗号学的ハッシュ関数](https://zh.wikipedia.org/wiki/%E5%AF%86%E7%A2%BC%E9%9B%9C%E6%B9%8A%E5%87%BD%E6%95%B8)で、128ビット(16[バイト](https://zh.wikipedia.org/wiki/%E5%AD%97%E8%8A%82))のハッシュ値(hash value)を生成し、情報の伝送が完全かつ一貫していることを確かめるために使われます。MD5 は米国の暗号学者[ロナルド・リベスト](https://zh.wikipedia.org/wiki/%E7%BD%97%E7%BA%B3%E5%BE%B7%C2%B7%E6%9D%8E%E7%BB%B4%E6%96%AF%E7%89%B9)(Ronald Linn Rivest)が設計し、1992年に公開されて、[MD4](https://zh.wikipedia.org/wiki/MD4) アルゴリズムに取って代わりました。このアルゴリズムの手順は [RFC 1321](https://tools.ietf.org/html/rfc1321) で規定されています。



擬似コードで表すと次のとおりです。

```
/Note: All variables are unsigned 32 bits and wrap modulo 2^32 when calculating
var int[64] r, k

//r specifies the per-round shift amounts
r[ 0..15]：= {7, 12, 17, 22,  7, 12, 17, 22,  7, 12, 17, 22,  7, 12, 17, 22} 
r[16..31]：= {5,  9, 14, 20,  5,  9, 14, 20,  5,  9, 14, 20,  5,  9, 14, 20}
r[32..47]：= {4, 11, 16, 23,  4, 11, 16, 23,  4, 11, 16, 23,  4, 11, 16, 23}
r[48..63]：= {6, 10, 15, 21,  6, 10, 15, 21,  6, 10, 15, 21,  6, 10, 15, 21}

//Use binary integer part of the sines of integers as constants:
for i from 0 to 63
    k[i] := floor(abs(sin(i + 1)) × 2^32)

//Initialize variables:
var int h0 := 0x67452301
var int h1 := 0xEFCDAB89
var int h2 := 0x98BADCFE
var int h3 := 0x10325476

//Pre-processing:
append "1" bit to message
append "0" bits until message length in bits ≡ 448 (mod 512)
append bit length of message as 64-bit little-endian integer to message

//Process the message in successive 512-bit chunks:
for each 512-bit chunk of message
    break chunk into sixteen 32-bit little-endian words w[i], 0 ≤ i ≤ 15

    //Initialize hash value for this chunk:
    var int a := h0
    var int b := h1
    var int c := h2
    var int d := h3

    //Main loop:
    for i from 0 to 63
        if 0 ≤ i ≤ 15 then
            f := (b and c) or ((not b) and d)
            g := i
        else if 16 ≤ i ≤ 31
            f := (d and b) or ((not d) and c)
            g := (5×i + 1) mod 16
        else if 32 ≤ i ≤ 47
            f := b xor c xor d
            g := (3×i + 5) mod 16
        else if 48 ≤ i ≤ 63
            f := c xor (b or (not d))
            g := (7×i) mod 16
 
        temp := d
        d := c
        c := b
        b := leftrotate((a + f + k[i] + w[g]),r[i]) + b
        a := temp
    Next i
    //Add this chunk's hash to result so far:
    h0 := h0 + a
    h1 := h1 + b 
    h2 := h2 + c
    h3 := h3 + d
End ForEach
var int digest := h0 append h1 append h2 append h3 //(expressed as little-endian)
```

際立った特徴は次のとおりです。

```c
    h0 = 0x67452301;
    h1 = 0xefcdab89;
    h2 = 0x98badcfe;
    h3 = 0x10325476;
```
