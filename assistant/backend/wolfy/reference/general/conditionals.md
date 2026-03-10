# Conditionals

In Soulver, a conditional is expressed on a single line:

```
earnings = $45k                                     | $45,000.00

if earnings > $30k then tax = 20% else tax = 5%     | 20%

My tax paid: earnings × tax                         | $9,000.00
```

**Declare a variable using a conditional**

```
income = $35k
expenses = $21.5k

profitable = true if income > expenses        | true
insolvent = false unless expenses > income    | false
```

**Using "and" and "or" in conditionals**

```
BMI = 24
Underweight = BMI < 18.5                        | false
Healthy Weight = BMI >= 18.5 and BMI < 25       | true
Overweight = BMI >= 25 and BMI < 30             | false
Obese = BMI >= 30                               | false
```

{% hint style="info" %}
&& and || are also supported
{% endhint %}

#### Comparison operators & booleans

Soulver supports standard ["C" style](https://en.wikipedia.org/wiki/C_\(programming_language\)) comparison operators.&#x20;

A boolean value (`true` or `false`) is returned).

| Name                     | Operator |
| ------------------------ | -------- |
| Equal to                 | ==       |
| Not equal to             | !=       |
| Greater than             | >        |
| Less than                | <        |
| Greater than or equal to | >=       |
| Less than or equal to    | <=       |

You may assign a variable a boolean value directly

```
cost = $500                                 
discount = true                        
if discount then cost = cost - 10%
cost                                    | $450.00
```

You can also use comparison operators outside if statements

```
20km == 20,000 m                        | true
11:30 am < 9:30 am                      | false
```
