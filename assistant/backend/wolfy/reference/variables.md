# Variables

### Declaring variables

Declare a variable with the equals symbol '='.

```
discount = 10%                         | 10%
cost = $550                            | $550
cost - discount                        | $495.00  
```

A variable can be a single word, or an entire phrase.

### Global variables

To declare variables that works across all sheets, go to `Settings > Calculator > Global Variables` and add a new variable by clicking the plus button.

### Redefining variables

A variable can be redefined by giving it a new value.&#x20;

The most recently defined value will be used on subsequent lines.

```
monthly rent = $1,900 // 2018      | $1,900
monthly rent = $2,150 // 2019      | $2,150                                   
monthly rent / 4 people            | $537.50
```

#### Variables can be added to and subtracted from

Use the `+=` and `-=` operators to modify the value of a variable

![](https://1915029247-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2F-Lf0gWBnuB8M1SitWhyk%2Fuploads%2FPJg3IACejDNthrxR6MRC%2Fimage.png?alt=media\&token=cba0ab26-b099-4fc7-84f5-d86478997910)

## Tips for working with variables

#### Peeking at a variable's value

On Mac, peek at a variable's value by holding down the shift key, and hovering over the variable.

<figure><img src="https://1915029247-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2F-Lf0gWBnuB8M1SitWhyk%2Fuploads%2F2x6Oww5MegC2MlIlMxsq%2Fimage.png?alt=media&#x26;token=686c9f0e-128e-41f0-b164-3286cbe99b67" alt="" width="158"><figcaption><p>Peeking at a variable value on Mac</p></figcaption></figure>

On iPad & iPhone, select a variable to peek at it's value.

<figure><img src="https://1915029247-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2F-Lf0gWBnuB8M1SitWhyk%2Fuploads%2FiAkARkOA0ORi7DM1EnFr%2Fimage.png?alt=media&#x26;token=14c2c77e-9fc2-4088-80d7-9bae057f9069" alt="" width="359"><figcaption><p>Peeking at a variable value on iPad &#x26; iPhone</p></figcaption></figure>

#### Auto-completing variable names

Instead of typing out a long variable name, you can press the **escape** key and then press **return** to quickly insert the entire variable name.

![Press escape to autocomplete long variable names](https://1915029247-files.gitbook.io/~/files/v0/b/gitbook-legacy-files/o/assets%2F-Lf0gWBnuB8M1SitWhyk%2F-LgXajgPmzwKN7WIDmhe%2F-LgXbGIw24ybhnbSEBGq%2FScreen%20Recording%202019-06-04%20at%2004.09%20pm.gif?alt=media\&token=93fefba9-4665-4c54-ac15-04e1b5389c23)

### Variable renaming (also known as refactoring)

When you rename a variable, Soulver will offer to automatically update any lines that reference your variable to use the new name.&#x20;

To invoke this feature, simply move the cursor to another line, after editing the name of a variable on a variable declaration line.

<div align="left"><figure><img src="https://1915029247-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2F-Lf0gWBnuB8M1SitWhyk%2Fuploads%2FMiukZpTx7AIzbVtjO2iP%2Fimage.png?alt=media&#x26;token=473b3183-6b37-4e32-a0ca-69a729d9800d" alt="" width="372"><figcaption></figcaption></figure></div>

## Things to note about variable declarations

#### Variables must be declared before use

You can't reference a variable *before* it has been declared.&#x20;

This behaviour is consistent with how variables work in programming languages (but differs from Soulver 2).

#### Currency rounding does not apply to variable declaration lines

When you declare a variable in a currency, it will be displayed **without rounding**  so it's unambiguous what the actual value stored in the variable is.

When used on subsequent lines, currency rounding will apply like usual.

<figure><img src="https://1915029247-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2F-Lf0gWBnuB8M1SitWhyk%2Fuploads%2FsCrP0F1CwZNv3TMtfLij%2Fimage.png?alt=media&#x26;token=9777fc7f-50db-485a-ad17-6d55db7879e5" alt="" width="563"><figcaption><p>It's clear what the actual value of "cost per day is"</p></figcaption></figure>

#### Variable declarations can be excluded from the floating total

Use the View > Total options menu to configure whether the floating total should include or exclude variable declaration lines

<figure><img src="https://1915029247-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2F-Lf0gWBnuB8M1SitWhyk%2Fuploads%2FO0c27X6I3nT6jfb0cY4A%2Fimage.png?alt=media&#x26;token=4eb970b7-12de-4583-a335-878b51f63a6e" alt="" width="563"><figcaption></figcaption></figure>
