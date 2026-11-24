# The Heap

ヒープは初期化時に `heap flags` を調べ、いくつかのフラグビットが設定されているかどうかに応じて、環境に追加の変更を加えます。`Themida` などは、この方法でデバッガを検出しています。

たとえば次のとおりです。

* `HEAP_TAIL_CHECKING_ENABLED` フラグ(`Heap Flags` の節を参照)が設定されていると、32ビットの Windows では、確保したヒープブロックの末尾に `0xABABABAB` が2つ付加されます(64ビット環境では4つです)。
* `HEAP_FREE_CHECKING_ENABLED` フラグ(`Heap Flags` の節を参照)が設定されていると、ヒープブロックの末尾を埋めるのに追加のバイトが必要なとき、`0xFEEEFEEE`(またはその一部)で埋められます。

そうすると、デバッガを検出する新しい方法として、これらの値を調べることが考えられます。

## ヒープポインタが既知の場合

ヒープポインタが1つ既知であれば、ヒープブロック内のデータを直接調べられます。ただし `Windows Vista` 以降のバージョンでは、ヒープ保護機構(32ビット・64ビットのどちらにもあります)が採用されており、XOR 鍵でヒープブロックのサイズが暗号化されています。鍵を使うかどうかは選べますが、既定では使われます。また、ヒープブロックのヘッダの位置も、`Windows NT/2000/XP` と `Windows Vista 以降のバージョン` とでは異なります。そのため、`Windows のバージョン` も考慮に入れる必要があります。

32ビット環境では、次の32ビットコードで検出できます。

``` asm
    xor ebx, ebx
    call GetVersion
    cmp al, 6
    sbb ebp, ebp
    jb l1
    ;Process Environment Block
    mov eax, fs:[ebx+30h]
    mov eax, [eax+18h] ;get process heap base
    mov ecx, [eax+24h] ;check for protected heap
    jecxz l1
    mov ecx, [ecx]
    test [eax+4ch], ecx
    cmovne ebx, [eax+50h] ;conditionally get heap key
l1: mov eax, <heap ptr>
    movzx edx, w [eax-8] ;size
    xor dx, bx
    movzx ecx, b [eax+ebp-1] ;overhead
    sub eax, ecx
    lea edi, [edx*8+eax]
    mov al, 0abh
    mov cl, 8
    repe scasb
    je being_debugged
```

64ビット環境では、次の64ビットコードで検出できます。

```
    xor ebx, ebx
    call GetVersion
    cmp al, 6
    sbb rbp, rbp
    jb l1
    ;Process Environment Block
    mov rax, gs:[rbx+60h]
    mov eax, [rax+30h] ;get process heap base
    mov ecx, [rax+40h] ;check for protected heap
    jrcxz l1
    mov ecx, [rcx+8]
    test [rax+7ch], ecx
    cmovne ebx, [rax+88h] ;conditionally get heap key
l1: mov eax, <heap ptr>
    movzx edx, w [rax-8] ;size
    xor dx, bx
    add edx, edx
    movzx ecx, b [rax+rbp-1] ;overhead
    sub eax, ecx
    lea edi, [rdx*8+rax]
    mov al, 0abh
    mov cl, 10h
    repe scasb
    je being_debugged
```

ここには32ビットコードで64ビット環境を検出する例はありません。64ビットのヒープは32ビットのヒープ関数では解析できないためです。


## ヒープポインタが未知の場合

ヒープポインタがわからない場合は、`kernel32` の `HeapWalk()` 関数や `ntdll` の `RtlWalkHeap()` 関数(あるいは `kernel32` の `GetCommandLine()` 関数)を使えます。返されるヒープサイズの値は自動的に復号されるため、Windows のバージョンを気にする必要はありません。

32ビット環境では、次の32ビットコードで検出できます。

``` asm
    mov ebx, offset l2
    ;get a pointer to a heap block
l1: push ebx
    mov eax, fs:[30h] ;Process Environment Block
    push d [eax+18h] ;save process heap base
    call HeapWalk
    cmp w [ebx+0ah], 4 ;find allocated block
    jne l1
    mov edi, [ebx] ;data pointer
    add edi, [ebx+4] ;data size
    mov al, 0abh
    push 8
    pop ecx
    repe scasb
    je being_debugged
    ...
l2: db 1ch dup (0) ;sizeof(PROCESS_HEAP_ENTRY)
```

64ビット環境では、次の64ビットコードで検出できます。

``` asm
    mov rbx, offset l2
    ;get a pointer to a heap block
l1: push rbx
    pop rdx
    push 60h
    pop rsi
    gs:lodsq ;Process Environment Block
    ;get a pointer to process heap base
    mov ecx, [rax+30h]
    call HeapWalk
    cmp w [rbx+0eh], 4 ;find allocated block
    jne l1
    mov edi, [rbx] ;data pointer
    add edi, [rbx+8] ;data size
    mov al, 0abh
    push 10h
    pop rcx
    repe scasb
    je being_debugged
    ...
l2: db 28h dup (0) ;sizeof(PROCESS_HEAP_ENTRY)
```

ここには32ビットコードで64ビット環境を検出する例はありません。64ビットのヒープは32ビットのヒープ関数では解析できないためです。

