# CheckRemoteDebuggerPresent

## CheckRemoteDebuggerPresent について

`kernel32` の `CheckRemoteDebuggerPresent()` 関数は、指定したプロセスがデバッグされているかどうかを検出するために使います。名前の中の `Remote` は、同じマシン上の別のプロセスを指します。

``` c
BOOL WINAPI CheckRemoteDebuggerPresent(
  _In_    HANDLE hProcess,
  _Inout_ PBOOL  pbDebuggerPresent
);
```

デバッガが存在する場合(通常は自分がデバッグされているかどうかの検出です)、この関数は `pbDebuggerPresent` が指す値を `0xffffffff` に設定します。

## 検出コード

32ビット環境では、次の32ビットコードで検出できます。

``` asm
push eax
push esp
push -1 ;GetCurrentProcess()
call CheckRemoteDebuggerPresent
pop eax
test eax, eax
jne being_debugged
```

64ビット環境では、次の64ビットコードで検出できます。

``` asm
enter 20h, 0
mov edx, ebp
or rcx, -1 ;GetCurrentProcess()
call CheckRemoteDebuggerPresent
leave
test ebp, ebp
jne being_debugged
```

## 回避の方法

たとえば次のようなコードがあるとします。

``` c++
int main(int argc, char *argv[])
{
    BOOL isDebuggerPresent = FALSE;
    if (CheckRemoteDebuggerPresent(GetCurrentProcess(), &isDebuggerPresent ))
    {
        if (isDebuggerPresent )
        {
            std::cout << "Stop debugging program!" << std::endl;
            exit(-1);
        }
    }
    return 0;
}
```

`isDebuggerPresent` の値を直接書き換えるか、ジャンプの条件を書き換えることで回避できます(`CheckRemoteDebuggerPresent` の戻り値ではないことに注意してください。その戻り値は、関数が正しく実行されたかどうかを表すものです)。

ただし、`CheckRemoteDebuggerPresent` というこの API 関数そのものを書き換えようとする場合は、まず、`CheckRemoteDebuggerPresent` が内部で `NtQueryInformationProcess` を呼び出して機能を実現していることを知っておく必要があります。そこで、`NtQueryInformationProcess` の戻り値を書き換える必要があります。これについては [NtQueryInformationProcess の章](./ntqueryinformationprocess.md)で説明します。
