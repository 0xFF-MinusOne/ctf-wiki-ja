# FILE 構造体


## FILE の紹介

FILE は、Linux システムの標準 IO ライブラリでファイルを表す構造体で、ファイルストリーム(file stream)と呼ばれます。
FILE 構造体は、プログラムが fopen などの関数を実行したときに作成され、ヒープ上に確保されます。この戻り値を受け取るために、FILE 構造体を指すポインタを定義することがよくあります。

FILE 構造体は libio.h で次のように定義されています。

```c
struct _IO_FILE {
  int _flags;		/* High-order word is _IO_MAGIC; rest is flags. */
#define _IO_file_flags _flags

  /* The following pointers correspond to the C++ streambuf protocol. */
  /* Note:  Tk uses the _IO_read_ptr and _IO_read_end fields directly. */
  char* _IO_read_ptr;	/* Current read pointer */
  char* _IO_read_end;	/* End of get area. */
  char* _IO_read_base;	/* Start of putback+get area. */
  char* _IO_write_base;	/* Start of put area. */
  char* _IO_write_ptr;	/* Current put pointer. */
  char* _IO_write_end;	/* End of put area. */
  char* _IO_buf_base;	/* Start of reserve area. */
  char* _IO_buf_end;	/* End of reserve area. */
  /* The following fields are used to support backing up and undo. */
  char *_IO_save_base; /* Pointer to start of non-current get area. */
  char *_IO_backup_base;  /* Pointer to first valid character of backup area */
  char *_IO_save_end; /* Pointer to end of non-current get area. */

  struct _IO_marker *_markers;

  struct _IO_FILE *_chain;

  int _fileno;
#if 0
  int _blksize;
#else
  int _flags2;
#endif
  _IO_off_t _old_offset; /* This used to be _offset but it's too small.  */

#define __HAVE_COLUMN /* temporary */
  /* 1+column number of pbase(); 0 is unknown. */
  unsigned short _cur_column;
  signed char _vtable_offset;
  char _shortbuf[1];

  /*  char* _save_gptr;  char* _save_egptr; */

  _IO_lock_t *_lock;
#ifdef _IO_USE_OLD_IO_FILE
};
struct _IO_FILE_complete
{
  struct _IO_FILE _file;
#endif
#if defined _G_IO_IO_FILE_VERSION && _G_IO_IO_FILE_VERSION == 0x20001
  _IO_off64_t _offset;
# if defined _LIBC || defined _GLIBCPP_USE_WCHAR_T
  /* Wide character stream stuff.  */
  struct _IO_codecvt *_codecvt;
  struct _IO_wide_data *_wide_data;
  struct _IO_FILE *_freeres_list;
  void *_freeres_buf;
# else
  void *__pad1;
  void *__pad2;
  void *__pad3;
  void *__pad4;

  size_t __pad5;
  int _mode;
  /* Make sure we don't get into trouble again.  */
  char _unused2[15 * sizeof (int) - 4 * sizeof (void *) - sizeof (size_t)];
#endif
};
```

プロセス内の FILE 構造体は _chain フィールドで相互に連結されてリンクリストを形成します。リストの先頭はグローバル変数 _IO_list_all で表され、この値からすべての FILE 構造体をたどれます。

標準 I/O ライブラリでは、プログラムの起動時に 3 つのファイルストリーム stdin、stdout、stderr が自動的にオープンされます。したがって初期状態では、_IO_list_all はこれらのファイルストリームから成るリストを指しています。ただし、この 3 つのファイルストリームは libc.so のデータセグメントにあることに注意してください。一方、fopen で作成したファイルストリームはヒープメモリ上に確保されます。

libc.so には stdin\stdout\stderr などのシンボルがあります。これらは FILE 構造体を指すポインタで、実体の構造体のシンボルは次のとおりです。

```
_IO_2_1_stderr_
_IO_2_1_stdout_
_IO_2_1_stdin_
```


ただし実際には、_IO_FILE 構造体は別の構造体 _IO_FILE_plus に包まれています。_IO_FILE_plus には、一連の関数ポインタを指す重要なポインタ vtable が含まれています。

libc 2.23 では、vtable のオフセットは 32 ビットで 0x94、64 ビットで 0xd8 です。

```
struct _IO_FILE_plus
{
	_IO_FILE    file;
	IO_jump_t   *vtable;
}
```

vtable は IO_jump_t 型のポインタで、IO_jump_t にはいくつかの関数ポインタが保存されています。後ほど、一連の標準 IO 関数の中でこれらの関数ポインタが呼び出される様子を見ます。

```
void * funcs[] = {
   1 NULL, // "extra word"
   2 NULL, // DUMMY
   3 exit, // finish
   4 NULL, // overflow
   5 NULL, // underflow
   6 NULL, // uflow
   7 NULL, // pbackfail
   
   8 NULL, // xsputn  #printf
   9 NULL, // xsgetn
   10 NULL, // seekoff
   11 NULL, // seekpos
   12 NULL, // setbuf
   13 NULL, // sync
   14 NULL, // doallocate
   15 NULL, // read
   16 NULL, // write
   17 NULL, // seek
   18 pwn,  // close
   19 NULL, // stat
   20 NULL, // showmanyc
   21 NULL, // imbue
};
```



## fread

fread は標準 IO ライブラリの関数で、ファイルストリームからデータを読み込みます。関数のプロトタイプは次のとおりです。

```
size_t fread ( void *buffer, size_t size, size_t count, FILE *stream) ;
```

* buffer: 読み込んだデータを格納するバッファ。

* size: 各レコードの長さを指定します。

* count: レコードの個数を指定します。

* stream: 対象のファイルストリーム。

* 戻り値: データバッファに読み込まれたレコードの個数を返します。

fread のコードは /libio/iofread.c にあり、関数名は _IO_fread ですが、実際の機能は子関数 _IO_sgetn で実装されています。

```
_IO_size_t
_IO_fread (buf, size, count, fp)
     void *buf;
     _IO_size_t size;
     _IO_size_t count;
     _IO_FILE *fp;
{
  ...
  bytes_read = _IO_sgetn (fp, (char *) buf, bytes_requested);
  ...
}
```

_IO_sgetn 関数の中では _IO_XSGETN が呼び出されます。_IO_XSGETN は _IO_FILE_plus.vtable 内の関数ポインタで、この関数を呼ぶときはまず vtable 内のポインタを取り出してから呼び出します。

```
_IO_size_t
_IO_sgetn (fp, data, n)
     _IO_FILE *fp;
     void *data;
     _IO_size_t n;
{
  return _IO_XSGETN (fp, data, n);
}
```

デフォルトでは、この関数ポインタは _IO_file_xsgetn 関数を指しています。

```
  if (fp->_IO_buf_base
	      && want < (size_t) (fp->_IO_buf_end - fp->_IO_buf_base))
	    {
	      if (__underflow (fp) == EOF)
		break;

	      continue;
	    }
```


## fwrite

fwrite も標準 IO ライブラリの関数で、ファイルストリームにデータを書き込みます。関数のプロトタイプは次のとおりです。

```
size_t fwrite(const void* buffer, size_t size, size_t count, FILE* stream);
```

* buffer: ポインタです。fwrite の場合は、書き込むデータのアドレスです。

* size: 書き込む内容 1 件あたりのバイト数。

* count: size バイトのデータ項目を書き込む個数。

* stream: 対象のファイルポインタ。

* 戻り値: 実際に書き込まれたデータ項目の個数 count。


fwrite のコードは /libio/iofwrite.c にあり、関数名は _IO_fwrite です。
_IO_fwrite では、主に _IO_XSPUTN を呼び出して書き込み機能を実現しています。

先ほどの _IO_FILE_plus の紹介から、_IO_XSPUTN は _IO_FILE_plus の vtable 内にあることがわかります。この関数を呼ぶには、まず vtable 内のポインタを取り出し、そこへジャンプして呼び出します。

```
written = _IO_sputn (fp, (const char *) buf, request);
```

_IO_XSPUTN に対応するデフォルトの関数 _IO_new_file_xsputn の中では、同じく vtable 内にある _IO_OVERFLOW が呼び出されます。

```
 /* Next flush the (full) buffer. */
      if (_IO_OVERFLOW (f, EOF) == EOF)
```


_IO_OVERFLOW がデフォルトで対応する関数は _IO_new_file_overflow です。

```
if (ch == EOF)
    return _IO_do_write (f, f->_IO_write_base,
			 f->_IO_write_ptr - f->_IO_write_base);
  if (f->_IO_write_ptr == f->_IO_buf_end ) /* Buffer is really full */
    if (_IO_do_flush (f) == EOF)
      return EOF;
```
_IO_new_file_overflow の内部では、最終的にシステムインタフェースの write 関数が呼び出されます。



## fopen

fopen は標準 IO ライブラリでファイルを開くために使われます。関数のプロトタイプは次のとおりです。

```   
FILE *fopen(char *filename, *type);
```

* filename: 対象ファイルのパス

* type: オープン方式の種類

* 戻り値: ファイルポインタを返します。

fopen の内部では FILE 構造体が作成され、いくつかの初期化処理が行われます。その過程を見てみましょう。

まず、fopen に対応する関数 __fopen_internal の内部で malloc 関数が呼び出され、FILE 構造体の領域が確保されます。このことから、FILE 構造体がヒープ上に格納されることがわかります。

```
*new_f = (struct locked_FILE *) malloc (sizeof (struct locked_FILE));
```

続いて、作成した FILE の vtable を初期化し、_IO_file_init を呼び出してさらに初期化を行います。
```
_IO_JUMPS (&new_f->fp) = &_IO_file_jumps;
_IO_file_init (&new_f->fp);
```

_IO_file_init 関数の初期化処理では、_IO_link_in が呼び出され、新しく確保された FILE が _IO_list_all を先頭とする FILE のリストに連結されます。
```
void
_IO_link_in (fp)
     struct _IO_FILE_plus *fp;
{
    if ((fp->file._flags & _IO_LINKED) == 0)
    {
      fp->file._flags |= _IO_LINKED;
      fp->file._chain = (_IO_FILE *) _IO_list_all;
      _IO_list_all = fp;
      ++_IO_list_all_stamp;
    }
}
```

その後、__fopen_internal 関数は _IO_file_fopen 関数を呼び出して対象ファイルを開きます。_IO_file_fopen はユーザが渡したオープンモードに応じてオープン処理を行い、最終的にシステムインタフェースの open 関数が呼び出されます。ここではこれ以上深入りしません。
```
if (_IO_file_fopen ((_IO_FILE *) new_f, filename, mode, is32) != NULL)
    return __fopen_maybe_mmap (&new_f->fp.file);
```

fopen の処理をまとめると次のとおりです。

* malloc で FILE 構造体を確保する
* FILE 構造体の vtable を設定する
* 確保した FILE 構造体を初期化する
* 初期化した FILE 構造体を FILE 構造体のリストに連結する
* システムコールを呼び出してファイルを開く

## fclose

fclose は標準 IO ライブラリでオープン済みのファイルを閉じるための関数で、その役割は fopen と逆です。

```
int fclose(FILE *stream)
```
機能: ファイルストリームを閉じます。fclose を使うと、バッファ内に最後まで残っているデータがディスク上のファイルに出力され、ファイルポインタと関連するバッファが解放されます。



fclose はまず _IO_unlink_it を呼び出して、指定された FILE を _chain のリストから外します。

```
if (fp->_IO_file_flags & _IO_IS_FILEBUF)
    _IO_un_link ((struct _IO_FILE_plus *) fp);
```

その後 _IO_file_close_it 関数が呼び出され、_IO_file_close_it はシステムインタフェースの close を呼び出してファイルを閉じます。

```
if (fp->_IO_file_flags & _IO_IS_FILEBUF)
    status = _IO_file_close_it (fp);
```

最後に vtable 内の _IO_FINISH が呼び出されます。これは _IO_file_finish 関数に対応しており、その中で free 関数が呼び出されて、先ほど確保された FILE 構造体が解放されます。

```
_IO_FINISH (fp);
```


## printf/puts

printf と puts はよく使われる出力関数です。printf の引数が '\n' で終わる単純な文字列の場合、printf は puts 関数に最適化され、改行文字が取り除かれます。


puts はソースコード上では _IO_puts として実装されており、この関数の処理は fwrite の流れとほぼ同じです。関数内部で同様に vtable 内の _IO_sputn が呼び出され、その結果 _IO_new_file_xsputn が実行され、最後にシステムインタフェースの write 関数が呼び出されます。

printf のコールスタックのバックトレースは次のとおりで、こちらも _IO_file_xsputn を通じて実現されています。

```
vfprintf+11
_IO_file_xsputn
_IO_file_overflow
funlockfile
_IO_file_write
write
```


