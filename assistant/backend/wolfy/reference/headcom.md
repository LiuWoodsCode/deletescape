# Headings & Comments

## Headings

Use the # character to indicate a heading line. Heading lines are emboldened and do not display an answer (even if there are numbers in the heading).

```
# This is a heading
```

{% hint style="info" %}
You can customise the size of headings, as well as their color (and the color of the # symbol itself) from Soulver's styling preferences. &#x20;

There is also an option to strip heading symbols when exporting into PDF or printing.
{% endhint %}

## Comments

If you want Soulver to ignore certain numbers on a line, use a comment, like a label or a double slash comment.

### labels

Use a label at the beginning of a line, using a colon:

```
Cost of 128 GB iPhone 16: $999                | $999.00
```

{% hint style="info" %}
Labels are automatically formatted in **bold.**
{% endhint %}

### // double slash comments

All numbers after two slashes are ignored:

```
// 1 + 2                         | 
1 + 2                            | 3
```

You can also add slash comments to the end of lines:

```
I spent $128 + $45 on clothes // on 10-02-2019       |  $173.00
```

### (parenthesis comments)

Numbers with additional commenting words inside parentheses are ignored:

```
$999 (for iPhone 16)                   | $999.00
```

### "inline comments"

You can "quote out" numbers in the middle of an expression to have them ignored:

```
Boing "747" is $386.8M                |  $386.8M
```

#### Comment Styles Summary

| Type         | Syntax        | Notes                                                                                                        |
| ------------ | ------------- | ------------------------------------------------------------------------------------------------------------ |
| Label        | **123:**      | Sometimes a space character is needed after the : to distinguish from a clock time (like 14:45)              |
| Double slash | // 123        | Commonly used in software languages. Press ⌘-/ to automatically comment out an entire line in this style.    |
| Parenthesis  | (123 comment) | Ensure you have an accompanying comment word inside the the parentheses, to prevent implicit multiplication. |
| Inline       | "123"         |                                                                                                              |
