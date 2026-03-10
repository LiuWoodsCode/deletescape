# Converting Units

Use `to` or `in` or `as` to convert into a particular unit.

```
10 km in m                          | 10,000 m
5 hours 30 minutes to seconds       | 19,800 seconds
100 pounds in kg                    | 45.36 kg
```

Or alternatively:

```
meters in 10 km                     | 10,000 m
days in 3 weeks                     | 21 days
seconds in a day                    | 86,400 s
```

{% hint style="success" %}
As a shorthand, you can also type two unit names without values to see the conversion:

"km m" (= 1,000 m)
{% endhint %}

Soulver uses unit symbols (rather than its full name) in the answer column.&#x20;

Control-click on an answer to see the full unit name

![](https://1915029247-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2F-Lf0gWBnuB8M1SitWhyk%2Fuploads%2FxSjIua2bsruFuAFT5yct%2Fimage.png?alt=media\&token=1ec1cca8-bf7b-486e-9a58-1fe9b0a1aa5d)

## Notes on Units

#### **Mixing Units & Plain Numbers**

When mixing plain numbers with units, the nearest unit will be used automatically. This is called **unit assimilation**.&#x20;

```
300 + 20 km                                              | 320 km
$20 + 30                                                 | $50.00
```

#### **Adding & Subtracting Mixed Units**

When doing calculations with mixed unit types, **the larger unit wins**:

```
1km + 1,000m                            | 2 km
```

When units don't share a common base unit, the **last used unit wins:**

```
$200 + €200                             | €308.84
```

#### **Multiplying Units**

Soulver only supports units that have been pre-defined in its math engine, not compound units that do "not exist":

```
10m × 10m                   | 100 m² // area, a supported unit type
3 kg × 3 liters             | // Not "9 kg liters", this unit does not exist
```

Soulver will make an implicit rate when a supported unit cannot be created through multiplication:

```
$30 × 4 days                                  | $120.00
// the above is interpreted as $30/day × 4 days
```

#### **Creating Custom Units**

You can add additional units to Soulver in the `Calculator > Custom Units` settings.&#x20;

{% hint style="info" %}
Custom units are defined in terms of an existing units.&#x20;

You cannot add new unit categories to Soulver (yet).
{% endhint %}
