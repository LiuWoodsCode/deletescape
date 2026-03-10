# Rounding

Specify the amount of decimal places to round an answer to. This will override the line's default precision settings.

```
# Rounding to a particular number of decimal places
1/3 to 2 dp                                    | 0.33
π to 5 digits                                  | 3.14159

# Rounding up and down
5.5 rounded                                    | 6
5.5 rounded down                               | 5
5.5 rounded up                                 | 6

# Rounding to nearest x
37 to nearest 10                               | 40
$490 rounded to nearest hundred                | $500
2,100 to nearest thousand                      | 2,000

# Rounding up and down to nearest x
21 rounded up to nearest 5                     | 25
17 rounded down to nearest 3                   | 15
```

Or use one of the following functions:

| Function | Name          | Behaviour                                        |
| -------- | ------------- | ------------------------------------------------ |
| round()  | Integer round | Rounds a number to the nearest integer           |
| ceil()   | Ceiling       | Rounds a number up to the nearest whole number   |
| floor()  | Floor         | Rounds a number down to the nearest whole number |
