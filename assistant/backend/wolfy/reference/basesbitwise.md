# Bases & Bitwise

### Decimal, Hex, Binary & Octal

Soulver supports base 2 (binary), octal (base 8) and hexadecimal (base 16), with various formats supported to convert between them

```
# Converters
256 as hex                           | 0x100
99 in binary                         | 0b1100011
0x9F31 to decimal                    | 40,753
0b1000101 to octal                   | 0o105

# Phrases
0b101101 as base 8                   | 0o55
0x2D as base 2                       | 0b101101

# Python-style functions
int(0o55)                            | 45
hex(99)                              | 0x63
bin(0x73)                            | 0b1110011
```

### Bitwise Operators

| Operator   | Name                |
| ---------- | ------------------- |
| & or AND   | Bitwise AND         |
| \| or OR   | Bitwise OR          |
| xor or XOR | Bitwise XOR         |
| <<         | Bitwise left shift  |
| >>         | Bitwise right shift |
