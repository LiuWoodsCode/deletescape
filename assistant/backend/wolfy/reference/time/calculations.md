# Clock Time Calculations

A clock time is a moment in time typically formatted with a colon (hh:mm)

### Adding or subtracting time from a clock time

<pre><code><strong>now + 3 hours 15 minutes                | 6:26 pm
</strong>9:45 am - 15 hours 10 minutes           | Yesterday at 6:35 pm
16:00 + 3 hours 12 minutes              | 7:12 pm
</code></pre>

{% hint style="info" %}
Daylight savings is taken into account when doing clock time calculations, and you might find unexpected results on days in which daylight savings time switches over.
{% endhint %}

### Finding the interval between two clock times

```
7:30 to 20:45                           | 3 hours 15 min
4pm to 3am                              | 11 hours
```

### Ambiguity when using the minus (-) operator with clock times

Sadly, the minus operator can be ambiguous when it comes to clock times.

Many of us use it to indicate a ***range of time*** from the **first clock time** to the **second clock time** (which is in the future):

`5pm - 9pm` (5pm to 9pm)

But many of us also use it to express a ***subtraction*** of second clock time from the first clock time:

`5pm - 3pm` (5pm minus 3pm)

Soulver does its best to try and interpret what you mean given the particular clock times you choose:

<pre><code>/// Get the amount of time between these two clock times today
5pm - 7pm                             | 2 hours
<strong>5pm - 2pm                             | 2 hours  
</strong>
// This is interpreted as 4 pm today back to 3am earlier this morning
4pm - 3am                             | 13 hours

/// This is interpreted as 3am earlier this morning to 4pm today
3am - 4pm                             | 13 hours
</code></pre>

For the most predictable results, use the "to" operator as described in [Finding the Interval between two clock times.](#finding-the-interval-between-two-clock-times)
