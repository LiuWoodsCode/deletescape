# Time Formats

{% hint style="success" %}
All time formats (units, timespans, laptimes & double time units) can be freely converted into each other
{% endhint %}

### Common Time Units

| Name   | Symbol | Definition        |
| ------ | ------ | ----------------- |
| Second | s, sec | Base unit of time |
| Minute | min    | 60 seconds        |
| Hour   | h, hr  | 60 minutes        |
| Day    | day    | 24 hours          |
| Week   | wk     | 7 days            |
| Month  | mo     | 30.436875 days    |
| Year   | yr     | 365.2425 days     |

### Timespans

A timespan is a quantity of time that displays multiple components (from the year down to the second)

```
5.5 minutes as timespan              | 5 min 30 s
4.54 hours as timespan               | 4 hours 32 minutes 24 seconds
72 days as timespan                  | 10 weeks 2 days
```

Timespans can be expressed and formatted in various ways

<pre><code>3 hours 5 minutes 10 seconds             | 3 hours 5 minutes 10 seconds
<strong>3h 5m 10s                                | 3 hours 5 minutes 10 seconds
</strong>
3h 5m 10s in seconds                     | 11,110 s
</code></pre>

### Laptimes

A laptime is a quantity of time in the format HH:MM:SS.MS (hour:minute:second.millisecond), commonly used by timers.

```
5.5 minutes as laptime               | 00:05:30
```

You can do arithmetic with laptimes:

```
03:04:05 + 01:02:03                    | 04:06:08
00:12:05 − 00:04:09                    | 00:07:56
```

{% hint style="info" %}
&#x20;A laptime must include two colons so Soulver can distinguish it from a clock time.&#x20;

For example, to specify a laptime of 1.5 seconds, use 00:00:01.5
{% endhint %}

You can convert between laptimes and timespans

```
03:04:05 as timespan                    | 3 hours 4 minutes 5 seconds
3 hours 4 minutes 5 seconds as laptime  | 03:04:05
```

### Double Time Units

```
12.5 minutes in minutes and seconds     | 12 min 30 s
1.4 weeks in hours and minutes          | 235 hours 12 min
4.5 weeks in days and hours             | 31 days 12 hours
```
