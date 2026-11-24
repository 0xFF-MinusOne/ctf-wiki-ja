# False Disassembly

`objdump` のような一般的な逆アセンブラや、`objdump` をベースにした逆アセンブラのプロジェクトには、逆アセンブルに関する欠陥があります。`objdump` が逆アセンブルしたコードをあまり正確でなくする方法がいくつかあります。

##  命令の途中へジャンプする

最も簡単な方法は、`jmp` で、ある命令の途中へジャンプして実行することです。つまり、本当のコードはある命令の「途中」から始まっています。しかし、逆アセンブルでは命令全体を単位とするため、実際に実行されるアセンブリ命令のコードを列挙できません。

言葉にすると回りくどくてわかりにくいので、例を見てみましょう。次のアセンブリコードがあるとします。

```
start:
	jmp label+1
label: 	
	DB 0x90
	mov eax, 0xf001
```

このコードで `label` がある最初の命令は `DB 0x90` です。`objdump` がこのコードを逆アセンブルした結果を見てみましょう。

```
08048080 <start>:
  8048080: 	e9 01 00 00 00 	jmp 8048086 <label+0x1>
08048085 <label>:
  8048085: 	90 		nop
  8048086: 	b8 01 f0 00 00 	mov eax,0xf001
```

特に問題はなさそうに見えます。`DB 0x90` は `90 nop` に正確に逆アセンブルされています。

しかし、`nop` 命令を1バイトより長い命令に変えると、objdump は jump をたどって正しく逆アセンブルしてくれません。上から下へ線形に逆アセンブルを続けます(リニアスイープ方式)。たとえば `DB 0x90` を `DB 0xE9` に変えて、objdump がもう一度逆アセンブルした結果を見てみましょう。

```
08048080 <start>:
  8048080: 	e9 01 00 00 00 	jmp 8048086 <label+0x1>
08048085 <label>:
  8048085: 	e9 b8 01 f0 00 	jmp 8f48242 <__bss_start+0xeff1b6>
```

先ほどの逆アセンブル結果と比べれば、何が起きているかは明らかでしょう。`DB 0xE9` は単なるデータで、実行されることもありません。ところが、逆アセンブルの結果ではそれを命令とみなしており、そのあとの結果もそれに伴って変わってしまいました。

objdump は `jmp の飛び先アドレスにあるコードを無視` して、jmp の直後の命令をそのまま逆アセンブルします。こうして、本当のコードはうまく「隠される」のです。

## 解決方法

この問題はどう解決すればよいでしょうか。最も直接的な方法は、この無用な `0xE9` を16進エディタで手動で `0x90` に置き換えることのようです。しかし、プログラムがファイルの検証を行い、checksum の値を計算している場合、この方法は通用しません。

そのため、より良い解決方法は、IDA のように制御フロー解析を行う逆アセンブラ、またはそれに類するものを使うことです。同じ問題のあるプログラムに対する逆アセンブル結果は、次のようになるでしょう。

```
  ---- section .text ----:
08048080 	E9 01 00 00 00 	jmp Label_08048086
			                                    ; (08048086)
			                                    ; (near + 0x1)
08048085 	DB E9

Label_08048086:
08048086	B8 01 F0 00 00	mov eax, 0xF001
			                                    ; xref ( 08048080 ) 
```

逆アセンブルの結果はまずまずに見えます。

## 実行時にジャンプ先アドレスを計算する

この方法は、制御フローを解析する逆アセンブラにさえ対抗できます。理解を深めるために、サンプルコードを見てみましょう。

```
; ----------------------------------------------------------------------------
    call earth+1
Return:
                    ; x instructions or random bytes here               x byte(s)
earth:              ; earth = Return + x
    xor eax, eax    ; align disassembly, using single byte opcode       1 byte
    pop eax         ; start of function: get return address ( Return )  1 byte
                    ; y instructions or random bytes here               y byte(s)
    add eax, x+2+y+2+1+1+z ; x+y+z+6                                    2 bytes
    push eax        ;                                                   1 byte
    ret             ;                                                   1 byte
                    ; z instructions or random bytes here               z byte(s)
; Code:
                    ; !! Code Continues Here !!
; ----------------------------------------------------------------------------
```

プログラムは `call+pop` で、関数を呼び出した時点でスタックに保存された戻りアドレスを取得します。これは実は関数呼び出し前の `EIP` です。そして、関数の戻り先にゴミデータを詰め込みます。しかし実際には、関数の実行中に戻りアドレスを Code の位置に書き換えてあります。そのため、`earth` 関数が戻ると `Return` ではなく `Code` にジャンプして実行を続けます。

簡単なデモを見てみましょう。

```
; ----------------------------------------------------------------------------
	call earth+1
earth: 	
    DB 0xE9 	        ; 1 <--- pushed return address,
		                ; E9 is opcode for jmp to disalign disas-
	; sembly
	pop eax 	        ; 1 hidden
	nop 	            ; 1
	add eax, 9 	        ; 2 hidden
	push eax 	        ; 1 hidden
	ret 	            ; 1 hidden
	DB 0xE9 	        ; 1 opcode for jmp to misalign disassembly
Code: 	                ; code continues here <--- pushed return address + 9
	nop
	nop
	nop
	ret
; ----------------------------------------------------------------------------
```

objdump で逆アセンブルすると、`call earth+1` の時点ですでに問題が生じます。次のとおりです。

```
00000000 <earth-0x5>:
  0: 	e8 01 00 00 00 	call 6 <earth+0x1>
00000005 <earth>:
  5: 	e9 58 90 05 09 	jmp 9059062 <earth+0x905905d>
  a: 	00 00 		    add %al,(%eax)
  c: 	00 50 c3 		add %dl,0xffffffc3(%eax)
  f: 	e9 90 90 90 c3 	jmp c39090a4 <earth+0xc390909f>
```

`ida` の場合も見てみましょう。

```
text:08000000 	; Segment permissions: Read/Execute
.text:08000000	 _text 	segment para public 'CODE' use32
.text:08000000 		assume cs:_text
.text:08000000 		;org 8000000h
.text:08000000 		assume 	es:nothing, ss:nothing, ds:_text,
.text:08000000 			fs:nothing, gs:nothing
.text:08000000 		dd 1E8h
.text:08000004 ; -------------------------------------------------------------
.text:08000004 		add cl, ch
.text:08000006 		pop eax
.text:08000007 		nop
.text:08000008 		add eax, 9
.text:0800000D 		push eax
.text:0800000E 		retn
.text:0800000E ; -------------------------------------------------------------
.text:0800000F 		dd 909090E9h
.text:08000013 ; -------------------------------------------------------------
.text:08000013 		retn
.text:08000013 _text 		ends
.text:08000013
.text:08000013
.text:08000013 		end
```

最後の3つの `nop` は、すべてうまく隠されています。それだけでなく、`EIP` を計算する過程も完全に隠されています。実際には、逆アセンブルされたコード全体が、実際のコードとはまったく違うものになっています。

この問題はどう解決すればよいでしょうか。実際には、`100%` 正確に逆アセンブルできると保証できるツールはなく、逆アセンブラがコードのエミュレーション実行までできるようになれば、完全に正しい逆アセンブルができるかもしれません。

現実には、これは特に大きな問題ではありません。対話型の逆アセンブラでは、コードの開始位置を自分で指定できるからです。また、デバッグするときにも、プログラムが実際にジャンプするアドレスをよく確認できます。

そのため、静的解析のほかに、動的デバッグも必要になります。




> Reference: [Beginners Guide to Basic Linux Anti Anti Debugging Techniques](http://www.stonedcoder.org/~kd/lib/14-61-1-PB.pdf)


