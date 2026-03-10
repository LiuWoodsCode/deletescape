# Converting Currencies

To perform a currency conversion, use the currency's 3 letter code, and convert using `in` or `to` or `as`:

```
10 USD in EUR                   | 8.88 EUR
20 GBP as AUD                   | 36.29 AUD
1500 RUB to DKK                 | 110.07 DKK
```

Soulver automatically downloads the latest exchange rates every hour. You can manually trigger a rate refresh from the `Settings` > `Currencies` pane.

### Historical currency conversions

You can perform a historical currency conversion which uses the rates on a particular date in the past:

<pre><code><strong>10 USD in EUR on March 20                | €8.37
</strong>1 BTC in USD one year ago                | $10,230.82
</code></pre>

{% hint style="info" %}
Historical currency rates are available for real-world currencies (back to 1999), and also for Bitcoin (back to 2013).&#x20;
{% endhint %}

### Currency conversions with custom rates

You can manually specify the rate you'd like used in a currency conversion:

<pre><code><strong>50 EUR in USD at 1.05 USD/EUR            | $52.50
</strong>50 EUR in RUB @ 80 RUB/EUR               | ₽4,000.00
</code></pre>

### **Currencies that use the dollar symbol ($)**

Soulver respects your Mac's region settings to determine which currency to use for the $ symbol.&#x20;

For example, if you live in Australia, $ will be tied to "AUD", rather than the default ("USD").

The following abbreviations are also supported:

<table data-full-width="false"><thead><tr><th>Symbol</th><th>Code</th><th>Currency</th></tr></thead><tbody><tr><td>US$</td><td>USD</td><td>United States Dollars</td></tr><tr><td>NZ$</td><td>NZD</td><td>New Zealand Dollars</td></tr><tr><td>C$, CA$</td><td>CAD</td><td>Canadian Dollars</td></tr><tr><td>A$, AU$</td><td>AUD</td><td>Australian Dollars</td></tr><tr><td>S$</td><td>SGD</td><td>Singapore Dollars</td></tr><tr><td>NT$</td><td>TWD</td><td>Taiwanese Dollars</td></tr><tr><td>HK$</td><td>HKD</td><td>Hong Kong Dollars</td></tr><tr><td>R$</td><td>BRL</td><td>Brazilian Reals</td></tr></tbody></table>

{% hint style="info" %}
You can customize the symbols for every currency in

`Settings > Calculator > Currency Symbols`.
{% endhint %}
