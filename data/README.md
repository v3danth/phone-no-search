# data/

## in_mobile_series.csv

Maps the first 4 digits of an Indian mobile number to its original operator
and telecom circle (DoT series allocations). Columns: series, operator,
circle, source. A value like `BR/WB` means the 4-digit block is split.

Sources (fetched 2026-11-06), in priority order:
1. `wikipedia`: tables in "Mobile telephone numbering in India",
   https://en.wikipedia.org/wiki/Mobile_telephone_numbering_in_India
   (CC BY-SA 4.0). 2,209 rows.
2. `in-mob-prefix`: https://github.com/hstsethi/in-mob-prefix (CC BY 4.0),
   used only where Wikipedia has no complete entry. 41 rows.
3. `partial`: only an operator or only a circle was known. 43 rows.

Because it includes Wikipedia content, this file is CC BY-SA 4.0: credit the
sources above and keep the same licence if you redistribute it.

Where both sources had a value they disagreed about 10% of the time
(70 operator, 95 circle mismatches out of 1,661). Wikipedia matched
numverify on the one checked conflict (7904), so it wins.

Caveats: ~2,250 of 4,000 prefixes covered; DoT really allocates 5-digit
blocks; results show the original allocation, not the current carrier.

Refresh:
    curl -sL -o wiki.txt 'https://en.wikipedia.org/w/index.php?title=Mobile_telephone_numbering_in_India&action=raw'
    python3 scripts/parse_wiki.py wiki.txt > wiki_series.csv
    python3 scripts/merge.py wiki_series.csv <in-mob-prefix merged csv> > data/in_mobile_series.csv
