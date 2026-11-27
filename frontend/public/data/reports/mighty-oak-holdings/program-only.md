# Forecast tieout: engine/data-v2/mighty-oak-holdings

As of **2026-08-31**, fiscal year FY26 (2026-02-01 to 2027-01-31). One money measure throughout: new-business ARR bookings (type = new_business, the arr column).
Profile `engine/config/profiles/mighty-oak-holdings`. Fit: cumulative incidence. Ranges from 2000 simulated draws, seed 0, drawing deal outcomes only.

## 1. Reconciliation

1726 rows in `deals.csv` (ARR $2,504,080,299.00); 1075 new-business rows included, 651 excluded.

New-business bookings fiscal year to date: **$27,447,759.00**.

| Month | Bookings |
|---|---|
| 2026-02 | $7,269,409.00 |
| 2026-03 | $3,889,160.00 |
| 2026-04 | $1,681,412.00 |
| 2026-05 | $6,158,077.00 |
| 2026-06 | $5,327,468.00 |
| 2026-07 | $681,454.00 |
| 2026-08 | $2,440,779.00 |

Pipeline flow, fiscal-year start to as-of (current amounts):

|  | Deals | ARR |
|---|---|---|
| open at fiscal-year start | 127 | $216,414,277.00 |
| created | 247 | $444,438,240.00 |
| won | 18 | $27,447,759.00 |
| lost | 225 | $431,434,537.00 |
| open at as-of | 131 | $201,970,221.00 |

Other motions, reconciled separately and excluded:

| Motion | Rows | ARR | Won FYTD |
|---|---|---|---|
| expansion | 300 | $110,577,998.00 | $29,415,198.00 |
| renewal | 351 | $346,753,004.00 | $93,779,695.00 |

| Check | Result | Detail |
|---|---|---|
| rows partition | pass | 1075 included + 651 excluded = 1726 of 1726 source rows |
| arr partition | pass | included + excluded arr = 2504080299 against source total 2504080299 (0 rows had no readable arr) |
| bookings tie to source | pass | source file new-business won FYTD 27447759 = included 27447759 + excluded rows 0 |
| pipeline flow | pass | open at FY start 216414277 + created 444438240 = won 27447759 + lost 431434537 + open now 201970221 |

Excluded rows by reason:

| Reason | Rows |
|---|---|
| excluded motion: expansion | 300 |
| excluded motion: renewal | 351 |

<details><summary>Every excluded row</summary>

| Row | Deal | Reason | ARR |
|---|---|---|---|
| 5 | MOH-00004 | excluded motion: expansion | $79,658.00 |
| 6 | MOH-00005 | excluded motion: renewal | $698,387.00 |
| 9 | MOH-00008 | excluded motion: expansion | $313,730.00 |
| 16 | MOH-00015 | excluded motion: renewal | $669,366.00 |
| 20 | MOH-00019 | excluded motion: expansion | $383,642.00 |
| 21 | MOH-00020 | excluded motion: renewal | $471,056.00 |
| 24 | MOH-00023 | excluded motion: renewal | $2,275,185.00 |
| 25 | MOH-00024 | excluded motion: renewal | $1,316,821.00 |
| 26 | MOH-00025 | excluded motion: renewal | $686,366.00 |
| 27 | MOH-00026 | excluded motion: expansion | $678,196.00 |
| 28 | MOH-00027 | excluded motion: renewal | $195,777.00 |
| 30 | MOH-00029 | excluded motion: renewal | $1,718,935.00 |
| 32 | MOH-00031 | excluded motion: expansion | $181,814.00 |
| 33 | MOH-00032 | excluded motion: renewal | $400,280.00 |
| 35 | MOH-00034 | excluded motion: expansion | $516,589.00 |
| 38 | MOH-00037 | excluded motion: renewal | $561,613.00 |
| 39 | MOH-00038 | excluded motion: renewal | $309,114.00 |
| 42 | MOH-00041 | excluded motion: expansion | $241,818.00 |
| 50 | MOH-00049 | excluded motion: expansion | $319,507.00 |
| 55 | MOH-00054 | excluded motion: renewal | $375,962.00 |
| 56 | MOH-00055 | excluded motion: renewal | $746,321.00 |
| 57 | MOH-00056 | excluded motion: renewal | $1,873,981.00 |
| 60 | MOH-00059 | excluded motion: renewal | $419,468.00 |
| 63 | MOH-00062 | excluded motion: renewal | $1,037,504.00 |
| 64 | MOH-00063 | excluded motion: renewal | $2,428,991.00 |
| 67 | MOH-00066 | excluded motion: expansion | $556,905.00 |
| 68 | MOH-00067 | excluded motion: expansion | $536,491.00 |
| 69 | MOH-00068 | excluded motion: renewal | $1,031,040.00 |
| 71 | MOH-00070 | excluded motion: expansion | $319,233.00 |
| 72 | MOH-00071 | excluded motion: renewal | $767,689.00 |
| 73 | MOH-00072 | excluded motion: expansion | $490,695.00 |
| 75 | MOH-00074 | excluded motion: renewal | $564,713.00 |
| 76 | MOH-00075 | excluded motion: renewal | $608,229.00 |
| 78 | MOH-00077 | excluded motion: renewal | $822,295.00 |
| 79 | MOH-00078 | excluded motion: renewal | $226,531.00 |
| 81 | MOH-00080 | excluded motion: renewal | $391,771.00 |
| 84 | MOH-00083 | excluded motion: expansion | $392,527.00 |
| 87 | MOH-00086 | excluded motion: expansion | $1,297,467.00 |
| 88 | MOH-00087 | excluded motion: renewal | $235,333.00 |
| 90 | MOH-00089 | excluded motion: renewal | $1,660,596.00 |
| 91 | MOH-00090 | excluded motion: expansion | $330,358.00 |
| 95 | MOH-00094 | excluded motion: renewal | $1,184,435.00 |
| 98 | MOH-00097 | excluded motion: renewal | $875,763.00 |
| 99 | MOH-00098 | excluded motion: renewal | $1,559,539.00 |
| 102 | MOH-00101 | excluded motion: expansion | $461,847.00 |
| 103 | MOH-00102 | excluded motion: renewal | $614,454.00 |
| 106 | MOH-00105 | excluded motion: renewal | $251,189.00 |
| 110 | MOH-00109 | excluded motion: renewal | $460,516.00 |
| 113 | MOH-00112 | excluded motion: expansion | $169,406.00 |
| 114 | MOH-00113 | excluded motion: renewal | $369,910.00 |
| 116 | MOH-00115 | excluded motion: expansion | $468,689.00 |
| 117 | MOH-00116 | excluded motion: renewal | $2,377,181.00 |
| 118 | MOH-00117 | excluded motion: renewal | $679,956.00 |
| 125 | MOH-00124 | excluded motion: expansion | $310,375.00 |
| 128 | MOH-00127 | excluded motion: expansion | $575,684.00 |
| 129 | MOH-00128 | excluded motion: expansion | $222,081.00 |
| 131 | MOH-00130 | excluded motion: renewal | $188,456.00 |
| 133 | MOH-00132 | excluded motion: renewal | $1,823,093.00 |
| 138 | MOH-00137 | excluded motion: renewal | $2,607,937.00 |
| 143 | MOH-00142 | excluded motion: renewal | $826,771.00 |
| 146 | MOH-00145 | excluded motion: renewal | $1,228,856.00 |
| 148 | MOH-00147 | excluded motion: renewal | $2,600,897.00 |
| 150 | MOH-00149 | excluded motion: expansion | $599,801.00 |
| 165 | MOH-00164 | excluded motion: expansion | $264,685.00 |
| 169 | MOH-00168 | excluded motion: renewal | $2,576,233.00 |
| 171 | MOH-00170 | excluded motion: renewal | $323,668.00 |
| 173 | MOH-00172 | excluded motion: renewal | $1,064,355.00 |
| 177 | MOH-00176 | excluded motion: renewal | $864,382.00 |
| 178 | MOH-00177 | excluded motion: expansion | $88,300.00 |
| 179 | MOH-00178 | excluded motion: renewal | $920,205.00 |
| 182 | MOH-00181 | excluded motion: expansion | $118,782.00 |
| 184 | MOH-00183 | excluded motion: renewal | $712,130.00 |
| 185 | MOH-00184 | excluded motion: renewal | $2,466,307.00 |
| 186 | MOH-00185 | excluded motion: expansion | $169,723.00 |
| 187 | MOH-00186 | excluded motion: renewal | $1,398,951.00 |
| 190 | MOH-00189 | excluded motion: expansion | $267,466.00 |
| 193 | MOH-00192 | excluded motion: renewal | $987,169.00 |
| 195 | MOH-00194 | excluded motion: renewal | $671,028.00 |
| 202 | MOH-00201 | excluded motion: renewal | $588,070.00 |
| 203 | MOH-00202 | excluded motion: renewal | $1,014,463.00 |
| 212 | MOH-00211 | excluded motion: expansion | $569,411.00 |
| 213 | MOH-00212 | excluded motion: expansion | $136,309.00 |
| 216 | MOH-00215 | excluded motion: renewal | $382,503.00 |
| 219 | MOH-00218 | excluded motion: renewal | $1,603,690.00 |
| 220 | MOH-00219 | excluded motion: expansion | $210,520.00 |
| 224 | MOH-00223 | excluded motion: expansion | $504,433.00 |
| 225 | MOH-00224 | excluded motion: expansion | $495,494.00 |
| 227 | MOH-00226 | excluded motion: expansion | $320,017.00 |
| 228 | MOH-00227 | excluded motion: expansion | $214,911.00 |
| 229 | MOH-00228 | excluded motion: renewal | $231,129.00 |
| 232 | MOH-00231 | excluded motion: expansion | $324,172.00 |
| 233 | MOH-00232 | excluded motion: renewal | $2,119,948.00 |
| 235 | MOH-00234 | excluded motion: renewal | $469,504.00 |
| 237 | MOH-00236 | excluded motion: expansion | $473,649.00 |
| 241 | MOH-00240 | excluded motion: renewal | $1,637,752.00 |
| 245 | MOH-00244 | excluded motion: renewal | $535,943.00 |
| 248 | MOH-00247 | excluded motion: renewal | $905,426.00 |
| 251 | MOH-00250 | excluded motion: renewal | $1,485,966.00 |
| 255 | MOH-00254 | excluded motion: renewal | $211,129.00 |
| 257 | MOH-00256 | excluded motion: renewal | $1,665,914.00 |
| 258 | MOH-00257 | excluded motion: expansion | $210,179.00 |
| 259 | MOH-00258 | excluded motion: renewal | $1,231,127.00 |
| 263 | MOH-00262 | excluded motion: renewal | $1,097,031.00 |
| 266 | MOH-00265 | excluded motion: expansion | $172,752.00 |
| 268 | MOH-00267 | excluded motion: expansion | $96,232.00 |
| 271 | MOH-00270 | excluded motion: expansion | $226,603.00 |
| 277 | MOH-00276 | excluded motion: renewal | $705,253.00 |
| 282 | MOH-00281 | excluded motion: expansion | $404,872.00 |
| 283 | MOH-00282 | excluded motion: renewal | $1,461,990.00 |
| 285 | MOH-00284 | excluded motion: renewal | $1,101,940.00 |
| 289 | MOH-00288 | excluded motion: renewal | $928,908.00 |
| 292 | MOH-00291 | excluded motion: renewal | $480,517.00 |
| 294 | MOH-00293 | excluded motion: renewal | $1,152,658.00 |
| 296 | MOH-00295 | excluded motion: expansion | $723,767.00 |
| 301 | MOH-00300 | excluded motion: expansion | $324,530.00 |
| 302 | MOH-00301 | excluded motion: renewal | $575,012.00 |
| 304 | MOH-00303 | excluded motion: expansion | $476,371.00 |
| 305 | MOH-00304 | excluded motion: expansion | $213,790.00 |
| 308 | MOH-00307 | excluded motion: expansion | $509,509.00 |
| 314 | MOH-00313 | excluded motion: expansion | $198,042.00 |
| 317 | MOH-00316 | excluded motion: expansion | $147,668.00 |
| 318 | MOH-00317 | excluded motion: renewal | $476,088.00 |
| 321 | MOH-00320 | excluded motion: expansion | $729,708.00 |
| 323 | MOH-00322 | excluded motion: expansion | $113,563.00 |
| 328 | MOH-00327 | excluded motion: expansion | $363,539.00 |
| 329 | MOH-00328 | excluded motion: renewal | $1,457,858.00 |
| 330 | MOH-00329 | excluded motion: expansion | $158,271.00 |
| 335 | MOH-00334 | excluded motion: expansion | $368,314.00 |
| 337 | MOH-00336 | excluded motion: renewal | $625,176.00 |
| 338 | MOH-00337 | excluded motion: renewal | $1,031,215.00 |
| 340 | MOH-00339 | excluded motion: expansion | $55,926.00 |
| 341 | MOH-00340 | excluded motion: renewal | $1,702,209.00 |
| 342 | MOH-00341 | excluded motion: expansion | $659,961.00 |
| 346 | MOH-00345 | excluded motion: expansion | $545,608.00 |
| 347 | MOH-00346 | excluded motion: expansion | $374,453.00 |
| 348 | MOH-00347 | excluded motion: expansion | $132,962.00 |
| 349 | MOH-00348 | excluded motion: expansion | $751,193.00 |
| 352 | MOH-00351 | excluded motion: renewal | $1,386,387.00 |
| 356 | MOH-00355 | excluded motion: expansion | $122,525.00 |
| 360 | MOH-00359 | excluded motion: renewal | $792,277.00 |
| 362 | MOH-00361 | excluded motion: expansion | $368,612.00 |
| 363 | MOH-00362 | excluded motion: expansion | $230,420.00 |
| 364 | MOH-00363 | excluded motion: renewal | $933,842.00 |
| 370 | MOH-00369 | excluded motion: renewal | $1,004,390.00 |
| 381 | MOH-00380 | excluded motion: renewal | $471,681.00 |
| 383 | MOH-00382 | excluded motion: expansion | $483,361.00 |
| 384 | MOH-00383 | excluded motion: renewal | $193,328.00 |
| 386 | MOH-00385 | excluded motion: renewal | $889,659.00 |
| 387 | MOH-00386 | excluded motion: expansion | $547,104.00 |
| 388 | MOH-00387 | excluded motion: renewal | $567,912.00 |
| 389 | MOH-00388 | excluded motion: expansion | $410,738.00 |
| 390 | MOH-00389 | excluded motion: expansion | $909,516.00 |
| 392 | MOH-00391 | excluded motion: expansion | $485,597.00 |
| 395 | MOH-00394 | excluded motion: renewal | $1,284,595.00 |
| 396 | MOH-00395 | excluded motion: expansion | $277,687.00 |
| 397 | MOH-00396 | excluded motion: expansion | $534,424.00 |
| 399 | MOH-00398 | excluded motion: expansion | $191,426.00 |
| 406 | MOH-00405 | excluded motion: expansion | $249,236.00 |
| 407 | MOH-00406 | excluded motion: renewal | $675,912.00 |
| 411 | MOH-00410 | excluded motion: expansion | $374,234.00 |
| 412 | MOH-00411 | excluded motion: renewal | $890,840.00 |
| 415 | MOH-00414 | excluded motion: expansion | $402,132.00 |
| 418 | MOH-00417 | excluded motion: expansion | $518,049.00 |
| 423 | MOH-00422 | excluded motion: expansion | $481,314.00 |
| 424 | MOH-00423 | excluded motion: renewal | $491,087.00 |
| 433 | MOH-00432 | excluded motion: renewal | $3,566,187.00 |
| 436 | MOH-00435 | excluded motion: expansion | $353,181.00 |
| 437 | MOH-00436 | excluded motion: renewal | $1,099,843.00 |
| 443 | MOH-00442 | excluded motion: renewal | $6,296,669.00 |
| 444 | MOH-00443 | excluded motion: renewal | $1,827,705.00 |
| 445 | MOH-00444 | excluded motion: renewal | $1,354,263.00 |
| 447 | MOH-00446 | excluded motion: renewal | $1,052,777.00 |
| 450 | MOH-00449 | excluded motion: expansion | $149,909.00 |
| 451 | MOH-00450 | excluded motion: renewal | $589,889.00 |
| 455 | MOH-00454 | excluded motion: expansion | $333,617.00 |
| 456 | MOH-00455 | excluded motion: expansion | $344,258.00 |
| 466 | MOH-00465 | excluded motion: expansion | $201,545.00 |
| 467 | MOH-00466 | excluded motion: renewal | $184,908.00 |
| 470 | MOH-00469 | excluded motion: expansion | $246,090.00 |
| 473 | MOH-00472 | excluded motion: renewal | $3,337,941.00 |
| 475 | MOH-00474 | excluded motion: renewal | $2,312,474.00 |
| 478 | MOH-00477 | excluded motion: expansion | $451,508.00 |
| 479 | MOH-00478 | excluded motion: renewal | $339,757.00 |
| 480 | MOH-00479 | excluded motion: renewal | $933,376.00 |
| 481 | MOH-00480 | excluded motion: expansion | $296,605.00 |
| 482 | MOH-00481 | excluded motion: renewal | $646,412.00 |
| 483 | MOH-00482 | excluded motion: renewal | $736,207.00 |
| 488 | MOH-00487 | excluded motion: renewal | $463,055.00 |
| 490 | MOH-00489 | excluded motion: expansion | $545,735.00 |
| 493 | MOH-00492 | excluded motion: renewal | $307,763.00 |
| 494 | MOH-00493 | excluded motion: expansion | $579,261.00 |
| 495 | MOH-00494 | excluded motion: expansion | $247,879.00 |
| 498 | MOH-00497 | excluded motion: expansion | $336,686.00 |
| 499 | MOH-00498 | excluded motion: renewal | $573,488.00 |
| 502 | MOH-00501 | excluded motion: expansion | $237,340.00 |
| 506 | MOH-00505 | excluded motion: expansion | $314,202.00 |
| 507 | MOH-00506 | excluded motion: renewal | $665,412.00 |
| 511 | MOH-00510 | excluded motion: expansion | $278,736.00 |
| 512 | MOH-00511 | excluded motion: expansion | $435,854.00 |
| 514 | MOH-00513 | excluded motion: renewal | $844,891.00 |
| 516 | MOH-00515 | excluded motion: renewal | $755,276.00 |
| 517 | MOH-00516 | excluded motion: renewal | $1,038,895.00 |
| 519 | MOH-00518 | excluded motion: renewal | $618,357.00 |
| 520 | MOH-00519 | excluded motion: renewal | $411,323.00 |
| 523 | MOH-00522 | excluded motion: expansion | $256,707.00 |
| 524 | MOH-00523 | excluded motion: renewal | $2,129,178.00 |
| 525 | MOH-00524 | excluded motion: expansion | $237,993.00 |
| 527 | MOH-00526 | excluded motion: expansion | $595,530.00 |
| 533 | MOH-00532 | excluded motion: renewal | $1,281,059.00 |
| 534 | MOH-00533 | excluded motion: renewal | $643,248.00 |
| 540 | MOH-00539 | excluded motion: renewal | $446,748.00 |
| 543 | MOH-00542 | excluded motion: expansion | $345,373.00 |
| 545 | MOH-00544 | excluded motion: expansion | $541,811.00 |
| 546 | MOH-00545 | excluded motion: renewal | $736,197.00 |
| 548 | MOH-00547 | excluded motion: expansion | $225,022.00 |
| 549 | MOH-00548 | excluded motion: renewal | $398,122.00 |
| 550 | MOH-00549 | excluded motion: renewal | $1,857,089.00 |
| 551 | MOH-00550 | excluded motion: renewal | $856,382.00 |
| 553 | MOH-00552 | excluded motion: renewal | $455,155.00 |
| 556 | MOH-00555 | excluded motion: renewal | $473,027.00 |
| 559 | MOH-00558 | excluded motion: renewal | $505,314.00 |
| 560 | MOH-00559 | excluded motion: renewal | $3,375,644.00 |
| 565 | MOH-00564 | excluded motion: expansion | $574,143.00 |
| 566 | MOH-00565 | excluded motion: expansion | $147,576.00 |
| 567 | MOH-00566 | excluded motion: renewal | $605,025.00 |
| 570 | MOH-00569 | excluded motion: renewal | $1,065,570.00 |
| 580 | MOH-00579 | excluded motion: expansion | $242,374.00 |
| 581 | MOH-00580 | excluded motion: expansion | $254,516.00 |
| 582 | MOH-00581 | excluded motion: renewal | $954,521.00 |
| 583 | MOH-00582 | excluded motion: renewal | $990,215.00 |
| 586 | MOH-00585 | excluded motion: expansion | $289,965.00 |
| 589 | MOH-00588 | excluded motion: expansion | $297,630.00 |
| 592 | MOH-00591 | excluded motion: renewal | $890,017.00 |
| 598 | MOH-00597 | excluded motion: expansion | $494,480.00 |
| 599 | MOH-00598 | excluded motion: expansion | $314,557.00 |
| 601 | MOH-00600 | excluded motion: renewal | $1,144,807.00 |
| 605 | MOH-00604 | excluded motion: expansion | $138,077.00 |
| 606 | MOH-00605 | excluded motion: expansion | $301,520.00 |
| 607 | MOH-00606 | excluded motion: expansion | $742,981.00 |
| 608 | MOH-00607 | excluded motion: expansion | $1,573,259.00 |
| 609 | MOH-00608 | excluded motion: renewal | $342,709.00 |
| 610 | MOH-00609 | excluded motion: expansion | $691,703.00 |
| 615 | MOH-00614 | excluded motion: renewal | $1,574,715.00 |
| 624 | MOH-00623 | excluded motion: renewal | $316,161.00 |
| 625 | MOH-00624 | excluded motion: expansion | $110,862.00 |
| 626 | MOH-00625 | excluded motion: expansion | $338,563.00 |
| 627 | MOH-00626 | excluded motion: expansion | $253,211.00 |
| 628 | MOH-00627 | excluded motion: renewal | $945,082.00 |
| 631 | MOH-00630 | excluded motion: expansion | $772,509.00 |
| 632 | MOH-00631 | excluded motion: expansion | $261,778.00 |
| 633 | MOH-00632 | excluded motion: renewal | $875,638.00 |
| 635 | MOH-00634 | excluded motion: renewal | $2,523,467.00 |
| 638 | MOH-00637 | excluded motion: expansion | $100,142.00 |
| 639 | MOH-00638 | excluded motion: expansion | $233,623.00 |
| 642 | MOH-00641 | excluded motion: expansion | $799,430.00 |
| 644 | MOH-00643 | excluded motion: renewal | $784,716.00 |
| 645 | MOH-00644 | excluded motion: renewal | $535,020.00 |
| 647 | MOH-00646 | excluded motion: renewal | $1,030,588.00 |
| 648 | MOH-00647 | excluded motion: expansion | $499,775.00 |
| 652 | MOH-00651 | excluded motion: expansion | $116,013.00 |
| 656 | MOH-00655 | excluded motion: expansion | $329,314.00 |
| 661 | MOH-00660 | excluded motion: expansion | $163,745.00 |
| 663 | MOH-00662 | excluded motion: expansion | $333,267.00 |
| 668 | MOH-00667 | excluded motion: renewal | $516,553.00 |
| 672 | MOH-00671 | excluded motion: renewal | $2,111,571.00 |
| 673 | MOH-00672 | excluded motion: expansion | $929,843.00 |
| 675 | MOH-00674 | excluded motion: renewal | $1,066,858.00 |
| 678 | MOH-00677 | excluded motion: renewal | $651,566.00 |
| 680 | MOH-00679 | excluded motion: renewal | $678,484.00 |
| 684 | MOH-00683 | excluded motion: renewal | $968,964.00 |
| 687 | MOH-00686 | excluded motion: expansion | $169,311.00 |
| 689 | MOH-00688 | excluded motion: renewal | $568,634.00 |
| 691 | MOH-00690 | excluded motion: expansion | $192,153.00 |
| 692 | MOH-00691 | excluded motion: renewal | $717,104.00 |
| 697 | MOH-00696 | excluded motion: renewal | $973,123.00 |
| 698 | MOH-00697 | excluded motion: renewal | $2,415,007.00 |
| 701 | MOH-00700 | excluded motion: renewal | $424,594.00 |
| 703 | MOH-00702 | excluded motion: renewal | $751,496.00 |
| 706 | MOH-00705 | excluded motion: expansion | $204,985.00 |
| 712 | MOH-00711 | excluded motion: expansion | $170,426.00 |
| 713 | MOH-00712 | excluded motion: renewal | $723,391.00 |
| 716 | MOH-00715 | excluded motion: renewal | $700,910.00 |
| 717 | MOH-00716 | excluded motion: renewal | $617,372.00 |
| 725 | MOH-00724 | excluded motion: expansion | $334,992.00 |
| 726 | MOH-00725 | excluded motion: renewal | $430,410.00 |
| 727 | MOH-00726 | excluded motion: renewal | $786,620.00 |
| 729 | MOH-00728 | excluded motion: expansion | $368,200.00 |
| 731 | MOH-00730 | excluded motion: renewal | $768,962.00 |
| 735 | MOH-00734 | excluded motion: renewal | $499,784.00 |
| 736 | MOH-00735 | excluded motion: expansion | $247,525.00 |
| 737 | MOH-00736 | excluded motion: expansion | $237,498.00 |
| 738 | MOH-00737 | excluded motion: renewal | $659,210.00 |
| 739 | MOH-00738 | excluded motion: expansion | $181,957.00 |
| 744 | MOH-00743 | excluded motion: renewal | $242,130.00 |
| 745 | MOH-00744 | excluded motion: expansion | $446,521.00 |
| 746 | MOH-00745 | excluded motion: renewal | $922,612.00 |
| 748 | MOH-00747 | excluded motion: expansion | $400,791.00 |
| 749 | MOH-00748 | excluded motion: expansion | $515,480.00 |
| 751 | MOH-00750 | excluded motion: renewal | $411,991.00 |
| 755 | MOH-00754 | excluded motion: expansion | $309,005.00 |
| 756 | MOH-00755 | excluded motion: expansion | $309,522.00 |
| 757 | MOH-00756 | excluded motion: renewal | $579,116.00 |
| 758 | MOH-00757 | excluded motion: renewal | $854,282.00 |
| 769 | MOH-00768 | excluded motion: expansion | $447,902.00 |
| 774 | MOH-00773 | excluded motion: expansion | $109,212.00 |
| 780 | MOH-00779 | excluded motion: renewal | $1,259,295.00 |
| 788 | MOH-00787 | excluded motion: expansion | $199,142.00 |
| 791 | MOH-00790 | excluded motion: expansion | $612,820.00 |
| 793 | MOH-00792 | excluded motion: renewal | $795,349.00 |
| 797 | MOH-00796 | excluded motion: renewal | $992,791.00 |
| 799 | MOH-00798 | excluded motion: expansion | $234,066.00 |
| 800 | MOH-00799 | excluded motion: expansion | $140,376.00 |
| 804 | MOH-00803 | excluded motion: expansion | $197,397.00 |
| 805 | MOH-00804 | excluded motion: renewal | $1,058,660.00 |
| 807 | MOH-00806 | excluded motion: expansion | $420,889.00 |
| 810 | MOH-00809 | excluded motion: expansion | $212,727.00 |
| 811 | MOH-00810 | excluded motion: expansion | $406,818.00 |
| 812 | MOH-00811 | excluded motion: renewal | $652,462.00 |
| 813 | MOH-00812 | excluded motion: renewal | $894,857.00 |
| 814 | MOH-00813 | excluded motion: expansion | $240,338.00 |
| 815 | MOH-00814 | excluded motion: expansion | $187,380.00 |
| 818 | MOH-00817 | excluded motion: expansion | $437,040.00 |
| 819 | MOH-00818 | excluded motion: renewal | $942,279.00 |
| 822 | MOH-00821 | excluded motion: renewal | $768,633.00 |
| 825 | MOH-00824 | excluded motion: renewal | $863,891.00 |
| 828 | MOH-00827 | excluded motion: expansion | $485,304.00 |
| 829 | MOH-00828 | excluded motion: renewal | $1,409,336.00 |
| 832 | MOH-00831 | excluded motion: expansion | $138,624.00 |
| 838 | MOH-00837 | excluded motion: renewal | $482,979.00 |
| 839 | MOH-00838 | excluded motion: expansion | $690,048.00 |
| 842 | MOH-00841 | excluded motion: expansion | $254,545.00 |
| 843 | MOH-00842 | excluded motion: expansion | $253,591.00 |
| 844 | MOH-00843 | excluded motion: expansion | $616,830.00 |
| 853 | MOH-00852 | excluded motion: expansion | $667,294.00 |
| 856 | MOH-00855 | excluded motion: renewal | $1,527,319.00 |
| 864 | MOH-00863 | excluded motion: expansion | $137,472.00 |
| 868 | MOH-00867 | excluded motion: expansion | $274,239.00 |
| 870 | MOH-00869 | excluded motion: renewal | $1,372,089.00 |
| 875 | MOH-00874 | excluded motion: expansion | $226,410.00 |
| 876 | MOH-00875 | excluded motion: expansion | $205,528.00 |
| 877 | MOH-00876 | excluded motion: renewal | $716,985.00 |
| 884 | MOH-00883 | excluded motion: renewal | $853,259.00 |
| 885 | MOH-00884 | excluded motion: renewal | $617,153.00 |
| 887 | MOH-00886 | excluded motion: expansion | $284,526.00 |
| 888 | MOH-00887 | excluded motion: renewal | $600,377.00 |
| 889 | MOH-00888 | excluded motion: renewal | $672,764.00 |
| 891 | MOH-00890 | excluded motion: renewal | $565,409.00 |
| 899 | MOH-00898 | excluded motion: expansion | $608,341.00 |
| 900 | MOH-00899 | excluded motion: renewal | $497,545.00 |
| 901 | MOH-00900 | excluded motion: renewal | $768,234.00 |
| 902 | MOH-00901 | excluded motion: renewal | $1,582,206.00 |
| 910 | MOH-00909 | excluded motion: renewal | $1,702,410.00 |
| 915 | MOH-00914 | excluded motion: expansion | $225,926.00 |
| 916 | MOH-00915 | excluded motion: renewal | $255,503.00 |
| 917 | MOH-00916 | excluded motion: expansion | $243,469.00 |
| 921 | MOH-00920 | excluded motion: expansion | $342,991.00 |
| 929 | MOH-00928 | excluded motion: expansion | $771,324.00 |
| 930 | MOH-00929 | excluded motion: renewal | $1,835,949.00 |
| 931 | MOH-00930 | excluded motion: renewal | $1,641,011.00 |
| 935 | MOH-00934 | excluded motion: expansion | $461,968.00 |
| 943 | MOH-00942 | excluded motion: expansion | $350,484.00 |
| 944 | MOH-00943 | excluded motion: expansion | $430,142.00 |
| 945 | MOH-00944 | excluded motion: expansion | $447,211.00 |
| 946 | MOH-00945 | excluded motion: expansion | $82,185.00 |
| 950 | MOH-00949 | excluded motion: renewal | $1,029,400.00 |
| 951 | MOH-00950 | excluded motion: renewal | $415,722.00 |
| 952 | MOH-00951 | excluded motion: renewal | $714,800.00 |
| 954 | MOH-00953 | excluded motion: expansion | $464,584.00 |
| 955 | MOH-00954 | excluded motion: renewal | $1,149,816.00 |
| 956 | MOH-00955 | excluded motion: renewal | $956,229.00 |
| 960 | MOH-00959 | excluded motion: expansion | $425,990.00 |
| 961 | MOH-00960 | excluded motion: expansion | $144,636.00 |
| 965 | MOH-00964 | excluded motion: expansion | $224,357.00 |
| 966 | MOH-00965 | excluded motion: expansion | $789,775.00 |
| 969 | MOH-00968 | excluded motion: renewal | $685,293.00 |
| 970 | MOH-00969 | excluded motion: renewal | $1,209,055.00 |
| 973 | MOH-00972 | excluded motion: renewal | $825,642.00 |
| 980 | MOH-00979 | excluded motion: renewal | $558,886.00 |
| 984 | MOH-00983 | excluded motion: expansion | $574,668.00 |
| 988 | MOH-00987 | excluded motion: expansion | $379,434.00 |
| 989 | MOH-00988 | excluded motion: renewal | $1,198,504.00 |
| 992 | MOH-00991 | excluded motion: renewal | $1,097,564.00 |
| 993 | MOH-00992 | excluded motion: renewal | $147,416.00 |
| 999 | MOH-00998 | excluded motion: renewal | $496,594.00 |
| 1007 | MOH-01006 | excluded motion: renewal | $991,558.00 |
| 1011 | MOH-01010 | excluded motion: renewal | $964,012.00 |
| 1015 | MOH-01014 | excluded motion: expansion | $112,927.00 |
| 1026 | MOH-01025 | excluded motion: renewal | $2,035,369.00 |
| 1027 | MOH-01026 | excluded motion: renewal | $458,202.00 |
| 1032 | MOH-01031 | excluded motion: expansion | $105,823.00 |
| 1033 | MOH-01032 | excluded motion: renewal | $583,392.00 |
| 1034 | MOH-01033 | excluded motion: expansion | $447,038.00 |
| 1035 | MOH-01034 | excluded motion: renewal | $264,799.00 |
| 1040 | MOH-01039 | excluded motion: expansion | $221,766.00 |
| 1041 | MOH-01040 | excluded motion: expansion | $273,821.00 |
| 1042 | MOH-01041 | excluded motion: renewal | $740,876.00 |
| 1045 | MOH-01044 | excluded motion: renewal | $549,949.00 |
| 1049 | MOH-01048 | excluded motion: renewal | $1,328,419.00 |
| 1051 | MOH-01050 | excluded motion: renewal | $684,645.00 |
| 1053 | MOH-01052 | excluded motion: expansion | $327,566.00 |
| 1055 | MOH-01054 | excluded motion: renewal | $426,843.00 |
| 1056 | MOH-01055 | excluded motion: renewal | $291,023.00 |
| 1058 | MOH-01057 | excluded motion: renewal | $693,808.00 |
| 1060 | MOH-01059 | excluded motion: renewal | $1,789,830.00 |
| 1063 | MOH-01062 | excluded motion: renewal | $910,612.00 |
| 1070 | MOH-01069 | excluded motion: renewal | $1,347,666.00 |
| 1072 | MOH-01071 | excluded motion: expansion | $162,670.00 |
| 1075 | MOH-01074 | excluded motion: expansion | $171,536.00 |
| 1079 | MOH-01078 | excluded motion: renewal | $420,426.00 |
| 1083 | MOH-01082 | excluded motion: expansion | $199,913.00 |
| 1084 | MOH-01083 | excluded motion: expansion | $240,259.00 |
| 1085 | MOH-01084 | excluded motion: expansion | $516,412.00 |
| 1086 | MOH-01085 | excluded motion: expansion | $519,709.00 |
| 1089 | MOH-01088 | excluded motion: expansion | $135,629.00 |
| 1090 | MOH-01089 | excluded motion: renewal | $1,256,546.00 |
| 1091 | MOH-01090 | excluded motion: renewal | $907,254.00 |
| 1093 | MOH-01092 | excluded motion: expansion | $368,112.00 |
| 1098 | MOH-01097 | excluded motion: renewal | $739,737.00 |
| 1102 | MOH-01101 | excluded motion: expansion | $221,855.00 |
| 1103 | MOH-01102 | excluded motion: renewal | $1,277,164.00 |
| 1105 | MOH-01104 | excluded motion: renewal | $1,040,991.00 |
| 1107 | MOH-01106 | excluded motion: renewal | $790,548.00 |
| 1109 | MOH-01108 | excluded motion: expansion | $227,372.00 |
| 1110 | MOH-01109 | excluded motion: renewal | $544,270.00 |
| 1114 | MOH-01113 | excluded motion: expansion | $187,944.00 |
| 1117 | MOH-01116 | excluded motion: renewal | $358,684.00 |
| 1122 | MOH-01121 | excluded motion: expansion | $476,764.00 |
| 1130 | MOH-01129 | excluded motion: expansion | $169,824.00 |
| 1131 | MOH-01130 | excluded motion: renewal | $1,223,970.00 |
| 1134 | MOH-01133 | excluded motion: renewal | $881,455.00 |
| 1141 | MOH-01140 | excluded motion: renewal | $1,515,567.00 |
| 1142 | MOH-01141 | excluded motion: renewal | $157,406.00 |
| 1145 | MOH-01144 | excluded motion: expansion | $182,276.00 |
| 1146 | MOH-01145 | excluded motion: renewal | $885,399.00 |
| 1148 | MOH-01147 | excluded motion: expansion | $160,217.00 |
| 1150 | MOH-01149 | excluded motion: renewal | $1,064,168.00 |
| 1152 | MOH-01151 | excluded motion: renewal | $1,818,159.00 |
| 1154 | MOH-01153 | excluded motion: expansion | $136,239.00 |
| 1163 | MOH-01162 | excluded motion: expansion | $408,509.00 |
| 1166 | MOH-01165 | excluded motion: renewal | $302,686.00 |
| 1168 | MOH-01167 | excluded motion: expansion | $267,198.00 |
| 1169 | MOH-01168 | excluded motion: expansion | $273,477.00 |
| 1170 | MOH-01169 | excluded motion: expansion | $470,471.00 |
| 1171 | MOH-01170 | excluded motion: renewal | $150,042.00 |
| 1173 | MOH-01172 | excluded motion: renewal | $442,265.00 |
| 1176 | MOH-01175 | excluded motion: expansion | $391,534.00 |
| 1180 | MOH-01179 | excluded motion: expansion | $174,340.00 |
| 1181 | MOH-01180 | excluded motion: expansion | $1,372,703.00 |
| 1185 | MOH-01184 | excluded motion: expansion | $661,853.00 |
| 1189 | MOH-01188 | excluded motion: renewal | $239,548.00 |
| 1192 | MOH-01191 | excluded motion: renewal | $618,725.00 |
| 1193 | MOH-01192 | excluded motion: expansion | $227,999.00 |
| 1194 | MOH-01193 | excluded motion: expansion | $572,369.00 |
| 1195 | MOH-01194 | excluded motion: renewal | $606,094.00 |
| 1196 | MOH-01195 | excluded motion: renewal | $304,036.00 |
| 1199 | MOH-01198 | excluded motion: renewal | $1,624,223.00 |
| 1204 | MOH-01203 | excluded motion: expansion | $69,239.00 |
| 1205 | MOH-01204 | excluded motion: renewal | $3,306,223.00 |
| 1210 | MOH-01209 | excluded motion: expansion | $571,482.00 |
| 1213 | MOH-01212 | excluded motion: expansion | $385,381.00 |
| 1214 | MOH-01213 | excluded motion: renewal | $1,101,168.00 |
| 1216 | MOH-01215 | excluded motion: renewal | $250,655.00 |
| 1217 | MOH-01216 | excluded motion: renewal | $481,572.00 |
| 1224 | MOH-01223 | excluded motion: renewal | $1,032,619.00 |
| 1225 | MOH-01224 | excluded motion: renewal | $582,536.00 |
| 1228 | MOH-01227 | excluded motion: renewal | $2,376,835.00 |
| 1229 | MOH-01228 | excluded motion: renewal | $1,423,181.00 |
| 1235 | MOH-01234 | excluded motion: renewal | $1,124,209.00 |
| 1237 | MOH-01236 | excluded motion: expansion | $451,531.00 |
| 1238 | MOH-01237 | excluded motion: renewal | $1,120,588.00 |
| 1240 | MOH-01239 | excluded motion: expansion | $338,853.00 |
| 1244 | MOH-01243 | excluded motion: expansion | $125,028.00 |
| 1245 | MOH-01244 | excluded motion: renewal | $718,428.00 |
| 1249 | MOH-01248 | excluded motion: expansion | $372,184.00 |
| 1251 | MOH-01250 | excluded motion: renewal | $833,222.00 |
| 1255 | MOH-01254 | excluded motion: expansion | $400,476.00 |
| 1256 | MOH-01255 | excluded motion: expansion | $765,627.00 |
| 1257 | MOH-01256 | excluded motion: expansion | $142,115.00 |
| 1258 | MOH-01257 | excluded motion: renewal | $357,692.00 |
| 1260 | MOH-01259 | excluded motion: expansion | $208,858.00 |
| 1261 | MOH-01260 | excluded motion: expansion | $705,162.00 |
| 1264 | MOH-01263 | excluded motion: renewal | $1,060,241.00 |
| 1268 | MOH-01267 | excluded motion: expansion | $383,418.00 |
| 1271 | MOH-01270 | excluded motion: renewal | $650,168.00 |
| 1272 | MOH-01271 | excluded motion: renewal | $1,316,252.00 |
| 1273 | MOH-01272 | excluded motion: expansion | $220,134.00 |
| 1276 | MOH-01275 | excluded motion: expansion | $128,193.00 |
| 1278 | MOH-01277 | excluded motion: expansion | $519,826.00 |
| 1279 | MOH-01278 | excluded motion: renewal | $2,224,659.00 |
| 1284 | MOH-01283 | excluded motion: renewal | $638,193.00 |
| 1285 | MOH-01284 | excluded motion: expansion | $534,886.00 |
| 1292 | MOH-01291 | excluded motion: expansion | $497,772.00 |
| 1293 | MOH-01292 | excluded motion: expansion | $372,448.00 |
| 1294 | MOH-01293 | excluded motion: renewal | $1,796,218.00 |
| 1295 | MOH-01294 | excluded motion: renewal | $1,090,762.00 |
| 1305 | MOH-01304 | excluded motion: renewal | $363,116.00 |
| 1311 | MOH-01310 | excluded motion: renewal | $657,009.00 |
| 1312 | MOH-01311 | excluded motion: renewal | $742,974.00 |
| 1319 | MOH-01318 | excluded motion: expansion | $598,339.00 |
| 1320 | MOH-01319 | excluded motion: expansion | $123,542.00 |
| 1321 | MOH-01320 | excluded motion: renewal | $307,769.00 |
| 1322 | MOH-01321 | excluded motion: renewal | $968,990.00 |
| 1324 | MOH-01323 | excluded motion: expansion | $739,716.00 |
| 1325 | MOH-01324 | excluded motion: renewal | $1,632,426.00 |
| 1327 | MOH-01326 | excluded motion: expansion | $987,512.00 |
| 1330 | MOH-01329 | excluded motion: expansion | $573,148.00 |
| 1331 | MOH-01330 | excluded motion: expansion | $872,217.00 |
| 1332 | MOH-01331 | excluded motion: renewal | $1,210,615.00 |
| 1335 | MOH-01334 | excluded motion: renewal | $592,696.00 |
| 1336 | MOH-01335 | excluded motion: renewal | $1,460,220.00 |
| 1340 | MOH-01339 | excluded motion: expansion | $645,219.00 |
| 1341 | MOH-01340 | excluded motion: expansion | $289,984.00 |
| 1342 | MOH-01341 | excluded motion: renewal | $679,661.00 |
| 1343 | MOH-01342 | excluded motion: renewal | $890,400.00 |
| 1344 | MOH-01343 | excluded motion: renewal | $749,732.00 |
| 1345 | MOH-01344 | excluded motion: renewal | $1,855,460.00 |
| 1347 | MOH-01346 | excluded motion: expansion | $321,244.00 |
| 1348 | MOH-01347 | excluded motion: renewal | $514,788.00 |
| 1350 | MOH-01349 | excluded motion: renewal | $1,331,925.00 |
| 1353 | MOH-01352 | excluded motion: renewal | $1,197,266.00 |
| 1354 | MOH-01353 | excluded motion: renewal | $1,870,172.00 |
| 1359 | MOH-01358 | excluded motion: expansion | $528,345.00 |
| 1360 | MOH-01359 | excluded motion: expansion | $645,636.00 |
| 1362 | MOH-01361 | excluded motion: renewal | $2,396,440.00 |
| 1363 | MOH-01362 | excluded motion: expansion | $360,825.00 |
| 1364 | MOH-01363 | excluded motion: renewal | $289,631.00 |
| 1365 | MOH-01364 | excluded motion: expansion | $646,168.00 |
| 1370 | MOH-01369 | excluded motion: expansion | $486,172.00 |
| 1371 | MOH-01370 | excluded motion: expansion | $316,886.00 |
| 1372 | MOH-01371 | excluded motion: renewal | $811,232.00 |
| 1373 | MOH-01372 | excluded motion: renewal | $1,156,465.00 |
| 1374 | MOH-01373 | excluded motion: expansion | $229,023.00 |
| 1375 | MOH-01374 | excluded motion: expansion | $215,619.00 |
| 1377 | MOH-01376 | excluded motion: expansion | $441,016.00 |
| 1382 | MOH-01381 | excluded motion: expansion | $78,072.00 |
| 1383 | MOH-01382 | excluded motion: renewal | $827,618.00 |
| 1385 | MOH-01384 | excluded motion: renewal | $783,197.00 |
| 1387 | MOH-01386 | excluded motion: renewal | $1,045,021.00 |
| 1390 | MOH-01389 | excluded motion: expansion | $769,781.00 |
| 1391 | MOH-01390 | excluded motion: renewal | $1,558,417.00 |
| 1395 | MOH-01394 | excluded motion: expansion | $572,884.00 |
| 1396 | MOH-01395 | excluded motion: expansion | $347,148.00 |
| 1397 | MOH-01396 | excluded motion: renewal | $1,545,487.00 |
| 1401 | MOH-01400 | excluded motion: expansion | $76,580.00 |
| 1402 | MOH-01401 | excluded motion: renewal | $724,776.00 |
| 1403 | MOH-01402 | excluded motion: renewal | $1,017,097.00 |
| 1412 | MOH-01411 | excluded motion: renewal | $696,073.00 |
| 1415 | MOH-01414 | excluded motion: expansion | $324,151.00 |
| 1422 | MOH-01421 | excluded motion: expansion | $391,212.00 |
| 1424 | MOH-01423 | excluded motion: renewal | $3,367,275.00 |
| 1426 | MOH-01425 | excluded motion: expansion | $815,596.00 |
| 1427 | MOH-01426 | excluded motion: renewal | $478,681.00 |
| 1428 | MOH-01427 | excluded motion: renewal | $830,312.00 |
| 1433 | MOH-01432 | excluded motion: renewal | $743,246.00 |
| 1434 | MOH-01433 | excluded motion: renewal | $771,456.00 |
| 1437 | MOH-01436 | excluded motion: expansion | $822,666.00 |
| 1438 | MOH-01437 | excluded motion: renewal | $549,352.00 |
| 1442 | MOH-01441 | excluded motion: expansion | $257,231.00 |
| 1443 | MOH-01442 | excluded motion: renewal | $1,554,281.00 |
| 1446 | MOH-01445 | excluded motion: expansion | $255,108.00 |
| 1447 | MOH-01446 | excluded motion: renewal | $399,605.00 |
| 1449 | MOH-01448 | excluded motion: renewal | $1,288,552.00 |
| 1450 | MOH-01449 | excluded motion: expansion | $270,286.00 |
| 1451 | MOH-01450 | excluded motion: expansion | $264,485.00 |
| 1452 | MOH-01451 | excluded motion: expansion | $285,138.00 |
| 1454 | MOH-01453 | excluded motion: expansion | $773,192.00 |
| 1461 | MOH-01460 | excluded motion: renewal | $849,596.00 |
| 1462 | MOH-01461 | excluded motion: renewal | $617,987.00 |
| 1464 | MOH-01463 | excluded motion: renewal | $361,542.00 |
| 1465 | MOH-01464 | excluded motion: renewal | $1,182,062.00 |
| 1469 | MOH-01468 | excluded motion: renewal | $834,874.00 |
| 1472 | MOH-01471 | excluded motion: renewal | $844,903.00 |
| 1474 | MOH-01473 | excluded motion: expansion | $192,208.00 |
| 1476 | MOH-01475 | excluded motion: renewal | $1,337,953.00 |
| 1478 | MOH-01477 | excluded motion: renewal | $869,423.00 |
| 1480 | MOH-01479 | excluded motion: renewal | $680,067.00 |
| 1487 | MOH-01486 | excluded motion: expansion | $318,990.00 |
| 1488 | MOH-01487 | excluded motion: renewal | $2,355,519.00 |
| 1491 | MOH-01490 | excluded motion: renewal | $364,947.00 |
| 1493 | MOH-01492 | excluded motion: expansion | $398,908.00 |
| 1494 | MOH-01493 | excluded motion: renewal | $1,537,649.00 |
| 1496 | MOH-01495 | excluded motion: renewal | $2,226,081.00 |
| 1498 | MOH-01497 | excluded motion: expansion | $62,987.00 |
| 1501 | MOH-01500 | excluded motion: expansion | $230,279.00 |
| 1502 | MOH-01501 | excluded motion: expansion | $319,331.00 |
| 1505 | MOH-01504 | excluded motion: renewal | $1,038,852.00 |
| 1508 | MOH-01507 | excluded motion: renewal | $2,889,671.00 |
| 1510 | MOH-01509 | excluded motion: expansion | $312,525.00 |
| 1511 | MOH-01510 | excluded motion: renewal | $1,070,439.00 |
| 1512 | MOH-01511 | excluded motion: expansion | $432,338.00 |
| 1514 | MOH-01513 | excluded motion: renewal | $1,231,050.00 |
| 1521 | MOH-01520 | excluded motion: renewal | $1,008,755.00 |
| 1526 | MOH-01525 | excluded motion: renewal | $712,721.00 |
| 1528 | MOH-01527 | excluded motion: expansion | $364,084.00 |
| 1529 | MOH-01528 | excluded motion: expansion | $274,282.00 |
| 1530 | MOH-01529 | excluded motion: expansion | $265,324.00 |
| 1531 | MOH-01530 | excluded motion: expansion | $396,102.00 |
| 1533 | MOH-01532 | excluded motion: expansion | $236,262.00 |
| 1537 | MOH-01536 | excluded motion: expansion | $457,941.00 |
| 1538 | MOH-01537 | excluded motion: renewal | $1,166,486.00 |
| 1539 | MOH-01538 | excluded motion: renewal | $429,934.00 |
| 1540 | MOH-01539 | excluded motion: renewal | $627,762.00 |
| 1541 | MOH-01540 | excluded motion: expansion | $163,464.00 |
| 1542 | MOH-01541 | excluded motion: renewal | $684,959.00 |
| 1544 | MOH-01543 | excluded motion: renewal | $1,501,430.00 |
| 1547 | MOH-01546 | excluded motion: expansion | $348,825.00 |
| 1554 | MOH-01553 | excluded motion: expansion | $432,636.00 |
| 1555 | MOH-01554 | excluded motion: expansion | $291,371.00 |
| 1559 | MOH-01558 | excluded motion: renewal | $428,077.00 |
| 1566 | MOH-01565 | excluded motion: renewal | $442,179.00 |
| 1568 | MOH-01567 | excluded motion: expansion | $256,007.00 |
| 1569 | MOH-01568 | excluded motion: expansion | $376,247.00 |
| 1571 | MOH-01570 | excluded motion: expansion | $142,958.00 |
| 1575 | MOH-01574 | excluded motion: renewal | $855,825.00 |
| 1577 | MOH-01576 | excluded motion: renewal | $474,871.00 |
| 1581 | MOH-01580 | excluded motion: expansion | $561,063.00 |
| 1584 | MOH-01583 | excluded motion: renewal | $1,139,371.00 |
| 1588 | MOH-01587 | excluded motion: renewal | $947,132.00 |
| 1589 | MOH-01588 | excluded motion: renewal | $214,282.00 |
| 1591 | MOH-01590 | excluded motion: expansion | $433,670.00 |
| 1592 | MOH-01591 | excluded motion: renewal | $366,432.00 |
| 1593 | MOH-01592 | excluded motion: renewal | $479,684.00 |
| 1594 | MOH-01593 | excluded motion: expansion | $214,808.00 |
| 1596 | MOH-01595 | excluded motion: expansion | $265,015.00 |
| 1598 | MOH-01597 | excluded motion: expansion | $742,424.00 |
| 1599 | MOH-01598 | excluded motion: renewal | $884,102.00 |
| 1601 | MOH-01600 | excluded motion: expansion | $419,746.00 |
| 1605 | MOH-01604 | excluded motion: renewal | $1,162,515.00 |
| 1610 | MOH-01609 | excluded motion: renewal | $1,741,085.00 |
| 1611 | MOH-01610 | excluded motion: renewal | $547,187.00 |
| 1613 | MOH-01612 | excluded motion: renewal | $1,647,146.00 |
| 1623 | MOH-01622 | excluded motion: expansion | $403,088.00 |
| 1624 | MOH-01623 | excluded motion: expansion | $456,430.00 |
| 1627 | MOH-01626 | excluded motion: expansion | $117,540.00 |
| 1628 | MOH-01627 | excluded motion: renewal | $500,168.00 |
| 1633 | MOH-01632 | excluded motion: renewal | $1,220,365.00 |
| 1636 | MOH-01635 | excluded motion: renewal | $649,758.00 |
| 1637 | MOH-01636 | excluded motion: renewal | $1,045,718.00 |
| 1642 | MOH-01641 | excluded motion: renewal | $992,474.00 |
| 1644 | MOH-01643 | excluded motion: renewal | $195,256.00 |
| 1649 | MOH-01648 | excluded motion: expansion | $393,414.00 |
| 1652 | MOH-01652 | excluded motion: expansion | $442,660.00 |
| 1653 | MOH-01653 | excluded motion: renewal | $381,255.00 |
| 1663 | MOH-01664 | excluded motion: renewal | $768,705.00 |
| 1674 | MOH-01675 | excluded motion: expansion | $420,141.00 |
| 1676 | MOH-01678 | excluded motion: renewal | $535,019.00 |
| 1682 | MOH-01686 | excluded motion: expansion | $198,785.00 |
| 1684 | MOH-01689 | excluded motion: expansion | $125,367.00 |
| 1685 | MOH-01690 | excluded motion: expansion | $63,259.00 |
| 1693 | MOH-01699 | excluded motion: renewal | $1,711,061.00 |
| 1698 | MOH-01706 | excluded motion: renewal | $2,289,729.00 |

</details>

## 2. What the history can support

1075 new-business deals, first created 2024-02-01 (30 months before the as-of date); 944 closed outcomes; 24 monthly snapshots old enough to score a full horizon.

What cannot be reconstructed or relied on:

- stage_history.csv records stage changes only: it holds no past deal amounts and no past expected close dates
- deal_observations.csv supplies past amounts and expected close dates (3848 observations); a deal's state on a past date is its latest observation on or before that date
- 16 deals have no stage history, so they never appear in a win-rate snapshot; 1 of them are open: today's forecasts use their current stage from deals.csv, but at past cutoffs their stage is unknown and back-test folds leave them out
- win rates use snapshots from the trailing 24 months, young ones counted only for the days observed (the recency fit was adopted: lower mean absolute error at 1 and 3 months (1m: 3,234,094 vs 4,398,197; 3m: 11,625,581 vs 12,417,199))
- the model is pooled across segments; a segment split is not evaluated in this report
- roles on team_members.csv: ae 128, manager 7, renewal_manager 4, sdr 18, se 14, vp_sales 1; the capacity term is not shown (ramped AE-months varied 14% across the scored period; at least 20% is needed for headcount to be testable)
- team_members.csv holds no history of role, segment, quota or deal ownership: today's values stand in for every past date, and a deal's owner is its current owner

## 3. Three forecasts, side by side

| Method | Part | 2026-09 | 2026-10 | 2026-11 | 2026-12 | 2027-01 | 2027-02 | 2027-03 | 2027-04 | 2027-05 | 2027-06 | 2027-07 | 2027-08 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| trailing run-rate | run-rate | $5,144,544 | $5,316,029 | $5,144,544 | $5,316,029 | $5,316,029 | $4,801,574 | $5,316,029 | $5,144,544 | $5,316,029 | $5,144,544 | $5,316,029 | $5,316,029 | $62,591,952 |
| stage-weighted pipeline | existing pipeline | $19,428,410 | $2,625,879 | $2,055,497 | $1,136,779 | $2,015,980 | $1,603,733 | $64,969 | $0 | $0 | $0 | $0 | $0 | $28,931,248 |
| stage-weighted pipeline | future pipeline | $0 | $0 | $0 | $0 | $0 | $0 | $349,273 | $2,619,548 | $2,706,866 | $2,619,548 | $2,706,866 | $2,706,866 | $13,708,968 |
| fitted model | existing pipeline | $7,482,508 | $5,174,825 | $5,762,257 | $6,838,641 | $3,939,457 | $3,716,549 | $3,818,319 | $3,025,898 | $2,275,730 | $1,696,166 | $313,709 | $487,272 | $44,531,331 |
| fitted model | future pipeline | $0 | $141,833 | $408,894 | $1,280,842 | $2,162,645 | $2,660,823 | $3,968,145 | $4,620,426 | $5,695,616 | $6,033,921 | $6,711,929 | $6,786,805 | $40,471,879 |

Two windows:

| Method | rest of fiscal year (2026-09 to 2027-01) | next twelve months (2026-09 to 2027-08) |
|---|---|---|
| trailing run-rate | $26,237,174 | $62,591,952 |
| stage-weighted pipeline | $27,262,546 | $42,640,216 |
| fitted model | $33,191,902 | $85,003,210 |

Fitted-model ranges (1-month back-tested (80% range held 69% of 16 folds); 3-month too narrow (80% range held 36% of 14 folds); 6-month too narrow (80% range held 9% of 11 folds)):

Months: stretched by past misses; each month by the factors of the horizon it falls in, and months beyond six use the six-month factors.

- rest of fiscal year: Stretched by the model's own past misses, using what six-month forecasts needed. Evidence at this length is thin: 1 past six-month forecast could be scored, and the stretched range did not hold it. This window (Aug 31, 2026 to Jan 31, 2027) is not exactly the six-month forecast that was tested.
- next twelve months: Stretched by the model's own past misses, using what six-month forecasts needed. Evidence at this length is thin: 1 past six-month forecast could be scored, and the stretched range did not hold it. This window (Aug 31, 2026 to Aug 31, 2027) is longer than six months, so it uses the six-month factors.

| Month | Median | 80% range | 95% range |
|---|---|---|---|
| 2026-09 | $6,666,620 | $1,794,616 to $13,988,174 | $0 to $17,400,307 |
| 2026-10 | $4,140,650 | $0 to $11,152,674 | $0 to $14,975,942 |
| 2026-11 | $4,979,140 | $0 to $12,531,748 | $0 to $17,789,957 |
| 2026-12 | $6,914,100 | $0 to $16,544,945 | $0 to $22,752,950 |
| 2027-01 | $4,898,006 | $0 to $12,297,307 | $0 to $18,217,536 |
| 2027-02 | $5,170,530 | $0 to $12,881,535 | $0 to $20,214,494 |
| 2027-03 | $6,520,718 | $0 to $14,354,789 | $0 to $20,727,478 |
| 2027-04 | $6,529,105 | $0 to $14,481,491 | $0 to $21,640,587 |
| 2027-05 | $6,801,498 | $0 to $15,625,326 | $0 to $22,559,945 |
| 2027-06 | $6,510,640 | $0 to $16,244,173 | $0 to $23,383,606 |
| 2027-07 | $6,170,153 | $0 to $14,248,527 | $0 to $20,245,818 |
| 2027-08 | $5,795,046 | $0 to $14,270,231 | $0 to $20,683,595 |
| rest of fiscal year (Stretched on the low side by past misses; 95%: Stretched the same way; not separately tested; floored at zero) | $32,679,736 | $8,849,384 to $45,242,810 | $0 to $53,567,376 |
| next twelve months (Stretched on the low side by past misses; 95%: Stretched the same way; not separately tested) | $83,620,370 | $40,303,603 to $107,009,984 | $21,792,670 to $120,188,666 |

Assumptions:

- **trailing run-rate**: new-business bookings continue at the trailing 365-day rate of 171484.80 per day
- **stage-weighted pipeline**: open deals book at their amount times the profile's stage probability (stages.yaml), in the month of their expected close; past-due deals count in the first month; new pipeline is created at 2182956.67 ARR per day (trailing 365 days) and converts at the Discovery probability 0.04, closing 208 days after creation (median cycle of 38 trailing wins)
- **fitted model**: open deals book at their current amount times the fitted win rate for their stage and age, on the fitted close-timing distribution; new pipeline is created at 1.2110 deals per day and wins at the fitted creation-cohort rate 0.0910, averaging 1986317.81 ARR per win

## 4. Every rate once

Each rate has one definition, used everywhere it appears.

| Rate | Value | Numerator / denominator | Cohort | Horizon | n | Source |
|---|---|---|---|---|---|---|
| `win_within_horizon:S1` | 0.102064 (95%: 0.0773-0.1337) | 45 wins observed within 365 days / 540 deals open in S1 at their first snapshot in the trailing 24 months (70 still open at the cutoff) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 540 | fitted |
| `win_within_horizon:S2` | 0.198270 (95%: 0.1563-0.2482) | 56 wins observed within 365 days / 341 deals open in S2 at their first snapshot in the trailing 24 months (48 still open at the cutoff) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 341 | fitted |
| `win_within_horizon:S3` | 0.347911 (95%: 0.2779-0.4251) | 55 wins observed within 365 days / 178 deals open in S3 at their first snapshot in the trailing 24 months (24 still open at the cutoff) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 178 | fitted |
| `win_within_horizon:S4` | 0.525472 (95%: 0.435-0.6143) | 62 wins observed within 365 days / 124 deals open in S4 at their first snapshot in the trailing 24 months (12 still open at the cutoff) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 124 | fitted |
| `win_within_horizon:S5` | 0.883944 (95%: 0.7873-0.94) | 58 wins observed within 365 days / 71 deals open in S5 at their first snapshot in the trailing 24 months (5 still open at the cutoff) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 71 | fitted |
| `win_within_horizon:S1:0-90d` | 0.099783 | 43 wins observed within 365 days (+20 x stage rate) / 533 deals open in S1 aged 0-90d (435.5 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 533 | fitted |
| `win_within_horizon:S1:181d+` | 0.073688 | 1 wins observed within 365 days (+20 x stage rate) / 27 deals open in S1 aged 181d+ (21.3 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 27 | fitted |
| `win_within_horizon:S1:91-180d` | 0.076603 | 4 wins observed within 365 days (+20 x stage rate) / 67 deals open in S1 aged 91-180d (58.1 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 67 | fitted |
| `win_within_horizon:S2:0-90d` | 0.197349 | 48 wins observed within 365 days (+20 x stage rate) / 295 deals open in S2 aged 0-90d (247.8 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 295 | fitted |
| `win_within_horizon:S2:181d+` | 0.170520 | 5 wins observed within 365 days (+20 x stage rate) / 39 deals open in S2 aged 181d+ (31.9 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 39 | fitted |
| `win_within_horizon:S2:91-180d` | 0.176453 | 16 wins observed within 365 days (+20 x stage rate) / 119 deals open in S2 aged 91-180d (93.3 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 119 | fitted |
| `win_within_horizon:S3:0-90d` | 0.328555 | 30 wins observed within 365 days (+20 x stage rate) / 107 deals open in S3 aged 0-90d (91.2 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 107 | fitted |
| `win_within_horizon:S3:181d+` | 0.321799 | 11 wins observed within 365 days (+20 x stage rate) / 39 deals open in S3 aged 181d+ (35.6 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 39 | fitted |
| `win_within_horizon:S3:91-180d` | 0.376624 | 31 wins observed within 365 days (+20 x stage rate) / 88 deals open in S3 aged 91-180d (79.6 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 88 | fitted |
| `win_within_horizon:S4:0-90d` | 0.497060 | 17 wins observed within 365 days (+20 x stage rate) / 37 deals open in S4 aged 0-90d (34.7 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 37 | fitted |
| `win_within_horizon:S4:181d+` | 0.489314 | 23 wins observed within 365 days (+20 x stage rate) / 55 deals open in S4 aged 181d+ (42.2 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 55 | fitted |
| `win_within_horizon:S4:91-180d` | 0.491788 | 35 wins observed within 365 days (+20 x stage rate) / 76 deals open in S4 aged 91-180d (70.9 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 76 | fitted |
| `win_within_horizon:S5:0-90d` | 0.907155 | 5 wins observed within 365 days (+20 x stage rate) / 5 deals open in S5 aged 0-90d (5.0 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 5 | fitted |
| `win_within_horizon:S5:181d+` | 0.868025 | 29 wins observed within 365 days (+20 x stage rate) / 37 deals open in S5 aged 181d+ (35.6 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 37 | fitted |
| `win_within_horizon:S5:91-180d` | 0.903252 | 30 wins observed within 365 days (+20 x stage rate) / 35 deals open in S5 aged 91-180d (35.0 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 35 | fitted |
| `new_pipeline_win_rate` | 0.091018 (95%: 0.0715-0.1152) | 60 wins observed within 365 days / 857 deals created (127 still open at the cutoff) | new-business deals created 2024-09-01 to 2026-08-31 | 365 days | 857 | fitted |
| `mean_won_arr` | 1986317.813547 | booked ARR of those wins / 60 wins observed | new-business deals created 2024-09-01 to 2026-08-31 | 365 days | 60 | fitted |
| `mean_created_arr` | 1877318.065344 | ARR of created deals / 857 deals with a known amount | new-business deals created 2024-09-01 to 2026-08-31 | at creation | 857 | fitted |
| `created_deals_per_day` | 1.210959 | 442 deals created / 365 days | created 2025-09-01 to 2026-08-31 | trailing | 442 | fitted |
| `trailing_bookings_per_day` | 171484.800000 | 62591952.00 ARR booked / 365 days | closed 2025-09-01 to 2026-08-31 | trailing | 38 | fitted |
| `stage_probability:S1` | 0.040000 | probability that a deal in Discovery is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S2` | 0.100000 | probability that a deal in Qualification is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S3` | 0.220000 | probability that a deal in Technical Evaluation is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S4` | 0.450000 | probability that a deal in Business Case is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S5` | 0.720000 | probability that a deal in Negotiation is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `created_arr_per_day` | 2182956.673973 | 796779186.00 ARR created (first recorded amount) / 365 days | created 2025-09-01 to 2026-08-31 | trailing | 442 | fitted |
| `median_won_cycle_days` | 208 | median of days to close / 38 wins | closed 2025-09-01 to 2026-08-31 | trailing | 38 | fitted |
| `horizon_days` | 365 | days within which a win counts for a win rate |  |  | 0 | default |
| `smoothing_pseudo_observations` | 20 | pull of an age-group cell toward its stage rate |  |  | 0 | default |
| `min_timing_samples` | 20 | wins a stage needs for its own close timing |  |  | 0 | default |
| `trailing_days` | 365 | window for trailing rates |  |  | 0 | default |
| `recency_months` | 24 | trailing months of snapshots for the cumulative-incidence fit |  |  | 0 | default |
| `lever_cap_multiple` | 3 | cap on added pipeline, times trailing created pipeline |  |  | 0 | default |
| `simulation_draws` | 2000 | Monte Carlo draws behind the ranges |  |  | 0 | default |
| `ramp_weight:1` | 0.791008 (95%: 0.4733-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `ramp_weight:2` | 0.453341 (95%: 0.2345-0.8763) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `ramp_weight:3` | 0.836122 (95%: 0.5077-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `ramp_weight:4` | 0.561506 (95%: 0.3001-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `ramp_weight:5` | 0.696964 (95%: 0.4014-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `ramp_weight:6` | 1 (95%: 0.6702-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `ramp_weight:7` | 1 (95%: 0.6873-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `ramp_weight:8` | 1 (95%: 0.7308-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `ramp_weight:9` | 0.873378 (95%: 0.5299-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `ramp_weight:10` | 0.935954 (95%: 0.5973-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `ramp_weight:11` | 1 (95%: 0.6769-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 26 | fitted |
| `attrition_per_ae_month` | 0.010978 (95%: 0.0074-0.0158) | 29 departures / 2641.7 AE-months employed | 2024-02-01 to 2026-08-31 | per AE-month | 29 | fitted |
| `created_deals_per_ramped_ae_month` | 0.419963 | 442 deals created / 1052.47 ramped AE-months | trailing 365 days to 2026-08-31 | per ramped AE-month | 442 | fitted |
| `loaded_cost_per_ae_month` | 16000 | cash cost of one AE for one month (capacity.yaml) | capacity.yaml | unstated | 0 | entered |
| `program_cost_per_dollar_of_pipeline` | 0.050000 | cash cost per dollar of program pipeline created (capacity.yaml) | capacity.yaml | unstated | 0 | entered |
| `program_ramp_months` | 3 | months a program takes to reach its full monthly pipeline | capacity.yaml | unstated | 0 | entered |
| `capacity_min_staffing_variation` | 0.200000 | ramped AE-months must vary by this much across the scored period for capacity to be testable |  |  | 0 | default |
| `capacity_min_improvement` | 0.100000 | capacity's created-pipeline error must be this much lower than the flat rate's at both horizons |  |  | 0 | default |
| `capacity_min_folds` | 6 | folds needed at each scored horizon |  |  | 0 | default |
| `days_per_ae_month` | 30.437500 | days in one AE-month |  |  | 0 | default |

## 5. The gap

Forecast: fitted model (expected value). Gap = target - actual - forecast (positive = short).

| Quarter | Status | Target | Actual | Forecast | Expected | Gap | Expected 80% range |
|---|---|---|---|---|---|---|---|
| Q1FY26 | closed | $17,000,000 | $12,839,981 | $0 | $12,839,981 | $4,160,019 | $12,839,981 to $12,839,981 |
| Q2FY26 | closed | $19,000,000 | $12,166,999 | $0 | $12,166,999 | $6,833,001 | $12,166,999 to $12,166,999 |
| Q3FY26 | in progress | $22,000,000 | $2,440,779 | $12,799,166 | $15,239,945 | $6,760,055 | $6,696,242 to $22,496,550 |
| Q4FY26 | not started | $26,000,000 | $0 | $20,392,736 | $20,392,736 | $5,607,264 | $0 to $32,331,600 |

Fiscal year: target $84,000,000, actual to date $27,447,759, forecast rest of year $33,191,902, expected **$60,639,661** (80%: $36,297,143 to $72,690,569, Stretched on the low side by past misses; 95%: $27,447,759 to $81,015,135, Stretched the same way; not separately tested; floored at zero), gap **$23,360,339**.

Next twelve months (2026-09 to 2027-08): quarters with a target ending in the window (Q3FY26, Q4FY26, through 2027-01-31): target $48,000,000, actual to date $2,440,779, forecast $33,191,902, gap **$12,367,319**.

2027-02 to 2027-08: forecast $51,811,308 (months outside a targeted quarter (targets end 2027-01-31): bookings alone).

**Pipeline to meet the fiscal-year total, spread evenly, new-business pipeline added: feasible: $2,018,192,885.26.** Schedule: added evenly across the 5 months to the target's end; cap $2,390,337,558 (3 times the new-business pipeline created in the trailing 365 days). Forecast without it $60,639,661, with it $84,000,000, against $84,000,000. Bookings gained at the required amount: rest of fiscal year $23,360,339; next twelve months $173,367,159.
_'feasible' means achievable inside the model's bounds (fitted conversion and timing, the cap above), not operationally achievable._

**Pipeline to meet the next-twelve-months targets, spread evenly, new-business pipeline added: feasible: $1,068,462,037.02.** Schedule: added evenly across the 5 months to the target's end; cap $2,390,337,558 (3 times the new-business pipeline created in the trailing 365 days). Forecast without it $35,632,681, with it $48,000,000, against $48,000,000. Bookings gained at the required amount: rest of fiscal year $12,367,319; next twelve months $91,783,213.
_'feasible' means achievable inside the model's bounds (fitted conversion and timing, the cap above), not operationally achievable._

## 6. Back-test

Scoring (declared before building): per horizon, mean absolute dollar error over all folds; 'yes' only if the fitted model's error is lower than both baselines at 1 and 3 months; under 6 folds is 'not enough history to say'.

| Horizon | Folds | Method | Mean abs. error | Signed bias | 80% coverage | 95% coverage |
|---|---|---|---|---|---|---|
| 1 mo | 16 | trailing run-rate | $3,711,491 | $1,476,513 |  |  |
| 1 mo | 16 | stage-weighted pipeline | $15,347,335 | $15,347,335 |  |  |
| 1 mo | 16 | fitted model | $3,234,094 | $2,322,521 | 69% | 88% |
| 3 mo | 14 | trailing run-rate | $8,100,541 | $4,597,054 |  |  |
| 3 mo | 14 | stage-weighted pipeline | $11,938,497 | $11,743,223 |  |  |
| 3 mo | 14 | fitted model | $11,625,581 | $11,625,581 | 36% | 79% |
| 6 mo | 11 | trailing run-rate | $15,023,582 | $10,879,387 |  |  |
| 6 mo | 11 | stage-weighted pipeline | $8,168,053 | -$137,499 |  |  |
| 6 mo | 11 | fitted model | $28,491,477 | $28,491,477 | 9% | 27% |

Recency candidate (cumulative incidence) against the Goal 1 fit (matured snapshots), same folds. Rule: adopted only if the fitted model's mean absolute error is lower than the Goal 1 fit's at both 1 and 3 months, on the same folds (at least 6 at each).

| Horizon | Folds | matured snapshots | cumulative incidence |
|---|---|---|---|
| 1m | 16 | $4,398,197 | $3,234,094 |
| 3m | 14 | $12,417,199 | $11,625,581 |

**Adopted**: lower mean absolute error at 1 and 3 months (1m: 3,234,094 vs 4,398,197; 3m: 11,625,581 vs 12,417,199). The forecast, rates, ranges and verdict use the cumulative incidence fit.

Ranges stretched by the model's own past misses. Rule: adopted if there are at least 6 scored folds at 1 and at 3 months, pooled 80% coverage over 1 and 3 months is closer to 80% than the simulated range's on the same folds, and no horizon (1, 3 or 6 months) moves more than 10 points further from 80%; each side's factor is the smallest, never below 1, that would have put at least 90% of the eligible past folds inside on that side (a fold is eligible once its whole horizon has ended; at least 5 are needed).

| Horizon | Eligible folds | Scored folds | Simulated 80% coverage | Stretched 80% coverage | Median 80% width, simulated | Median 80% width, stretched | Lower factor | Upper factor |
|---|---|---|---|---|---|---|---|---|
| 1 mo | 16 | 11 | 6 of 11 (55%) | 9 of 11 (82%) | $11,341,863 | $12,906,370 | 1.5613 | 1.0000 |
| 3 mo | 14 | 7 | 1 of 7 (14%) | 7 of 7 (100%) | $22,933,518 | $32,210,689 | 1.6355 | 1.0000 |
| 6 mo | 11 | 1 | 0 of 1 (0%) | 0 of 1 (0%) | $33,875,732 | $54,871,788 | 2.2960 | 1.0000 |

**Adopted**: pooled over 1 and 3 months, 18 scored folds: simulated 7 held (39%), stretched 16 held (89%); the stretched coverage is closer to 80% and no horizon is more than 10 points further.

What the rule accepted: The stretch was one-sided: only the lower side was stretched. On the scored past dates it held 88.9% of actuals against a target of 80%. The six-month factors rest on 11 past six-month forecasts, of which 1 could be scored. The lower edge was floored at zero for: Q4FY26.

Method: Each side's factor is the ceil(90% of n)-th smallest of the factors the n eligible past forecasts would have needed: the plain empirical rule, not a finite-sample guarantee. Six-month factors come from overlapping forecasts (each shares five of its six months with its neighbors) and are noisier: 11 past six-month forecasts to learn from, 1 scored.

## 7. Verdicts

**The software is correct: yes.** 21 of 21 self-checks passed (runtime self-checks on this report's own numbers; the arithmetic is also checked on hand-calculated fixtures by the test suite (pytest engine/tests/tieout_core)).

| Check | Result | Detail |
|---|---|---|
| rows partition | pass | 1075 included + 651 excluded = 1726 of 1726 source rows |
| arr partition | pass | included + excluded arr = 2504080299 against source total 2504080299 (0 rows had no readable arr) |
| bookings tie to source | pass | source file new-business won FYTD 27447759 = included 27447759 + excluded rows 0 |
| pipeline flow | pass | open at FY start 216414277 + created 444438240 = won 27447759 + lost 431434537 + open now 201970221 |
| existing pipeline conserved | pass | open 201970221.00 = won in window 44531331.26 + won later 0.00 + not won 157438889.74 |
| lever agrees with forward function | pass | forward($2,018,192,885.26) = 84000000.0001 against target 84000000 |
| twelve-month lever agrees with forward function | pass | forward($1,068,462,037.02) = 48000000.0001 against target 48000000 |
| simulation centered on the expectation | pass | simulated mean 84,987,971.80 vs expected 85,003,210.25 (tolerance 1,486,624.72, 2000 draws) |
| forecast parts add up | pass | each method's total equals the sum of its months (largest difference 2.00E-20) |
| folds saw nothing after their cutoff | pass | 16 cutoffs rebuilt with as_known_at; each fold asserts its latest fact is on or before its cutoff |
| every rate defined once | pass | 59 rates in one registry |
| roster rows partition | pass | 128 quota-carrying + 44 other roles + 0 excluded = 172 of 172 roster rows |
| the forecast uses capacity exactly when it was adopted | pass | capacity decision: not shown; forecast uses the flat creation rate |
| wins credited plus unattributed equal bookings in the window | pass | 58355817.00 + 4236135.00 = 62591952.00 against 62591952.00 |
| each solvable quarter meets its target under the schedules solved up to and including it | pass | 1 solvable quarters re-run through the forward function, each with the schedules solved up to and including its own; 1 unreachable checked against the cap, the cap left and the selling window |
| the completed schedule books each quarter's stated bookings and surplus over target | pass | 2 quarters rebuilt by adding each quarter's own schedule to the no-pipeline forecast |
| cents booked in each quarter, re-derived from the solved schedule, match the stated yield | pass | 1 solved schedules re-run on their own |
| lead-time yields match an independent forward run on a probe schedule, and the count shares sum to one | pass | 4 quarters checked on a $250,000 probe in two parts; win share 0.0910, not 0.9090 |
| plan contributions sum to the difference | pass | rest of fiscal year: 83295.40 = 33275197.21 - 33191901.81; next twelve months: 1600600.21 = 86603810.44 - 85003210.23 |
| plan simulation centered on its expectation | pass | simulated mean 86,865,409.79 vs expected 86,603,810.44 (2000 draws) |
| program solve agrees with the forward function | pass | unreachable within bounds: forward(3007281482.38) = 79207625.42 against 84000000 |

**The forecast is better than the baselines: no.** the model's mean absolute error is not lower than every baseline: 3m: model 11,625,581 vs trailing run-rate 8,100,541.

## 8. Roster and capacity

**Capacity term: not shown.** ramped AE-months varied 14% across the scored period; at least 20% is needed for headcount to be testable.

Scored on created-pipeline dollars at 3 and 6 months on the back-test's folds; the per-rep rate is fitted only from data before each cutoff and applied to the ramped AE-months that actually occurred. Conditional on realized staffing: it asks whether headcount explains pipeline, not how well it forecasts.
Declared rule: adopted only if ramped AE-months varied by at least 20% across the scored period, the capacity rate's mean absolute error is at least 10% lower than the flat trailing rate's at both 3 and 6 months, and there are at least 6 folds at each.
The forecast, gap, plan and actions use the the flat trailing creation rate. An association in the history, not a promise: that a new hire adds pipeline at this rate is an assumption.

| Horizon | Folds | Flat trailing rate, mean abs. error | Capacity rate, mean abs. error | Improvement |
|---|---|---|---|---|
| 3 mo | 14 | $19,501,668 | $20,489,215 | -5.1% |
| 6 mo | 11 | $27,375,898 | $36,083,486 | -31.8% |

Ramped AE-months varied 14% across the scored period (2025-04-30 to 2026-08-31).

Roster: 172 rows; 128 quota-carrying people on file, 99 employed at the as-of date, 93.60 ramped equivalents, against a headcount target of 100 this month (monthly_ae_targets in targets.yaml: a comparison line only; it never creates a hire). 29 have left to date; 0 signed hires.

Counted, carrying no capacity: manager 7, renewal_manager 4, sdr 18, se 14, vp_sales 1.

**Ramp (fitted):** 26 reps observed from hire through their sixth month; 99 tenured reps alongside. created deals per rep by tenure month, relative to reps with twelve or more months' tenure in the same calendar month; 1 from the next tenure month on. Limit: ownership on deals.csv says who owns a deal, not who made it: deals handed to a new rep count as that rep's, so a fitted ramp can read faster than the true one.

| Tenure month | Weight | 95% range |
|---|---|---|
| 1 | 0.7910 | 0.4733 to 1.0000 |
| 2 | 0.4533 | 0.2345 to 0.8763 |
| 3 | 0.8361 | 0.5077 to 1.0000 |
| 4 | 0.5615 | 0.3001 to 1.0000 |
| 5 | 0.6970 | 0.4014 to 1.0000 |
| 6 | 1.0000 | 0.6702 to 1.0000 |
| 7 | 1.0000 | 0.6873 to 1.0000 |
| 8 | 1.0000 | 0.7308 to 1.0000 |
| 9 | 0.8734 | 0.5299 to 1.0000 |
| 10 | 0.9360 | 0.5973 to 1.0000 |
| 11 | 1.0000 | 0.6769 to 1.0000 |

**Attrition (fitted):** 0.01098 per AE-month, 29 departures over 2641.7 AE-months (95%: 0.00735 to 0.01577). Forward: an expectation in the headline (a constant daily hazard from this monthly rate); a random draw in the ranges; nobody is back-filled unless the plan says so.

**Created deals per ramped AE-month:** 0.419963 (442 deals over 1052.47 ramped AE-months, trailing 365 days to 2026-08-31).

Heads, ramped equivalents and departures by month (forward months are expectations):

| Month |  | Heads | Ramped | Departures | Headcount target |
|---|---|---|---|---|---|
| 2025-09 | past | 85 | 83.35 | 1 |  |
| 2025-10 | past | 85 | 83.67 | 1 |  |
| 2025-11 | past | 86 | 83.57 | 0 |  |
| 2025-12 | past | 86 | 84.71 | 0 |  |
| 2026-01 | past | 85 | 84.77 | 2 |  |
| 2026-02 | past | 89 | 86.50 | 0 | 89 |
| 2026-03 | past | 92 | 88.06 | 1 | 93 |
| 2026-04 | past | 95 | 91.04 | 1 | 96 |
| 2026-05 | past | 96 | 91.26 | 2 | 98 |
| 2026-06 | past | 96 | 90.89 | 2 | 98 |
| 2026-07 | past | 96 | 92.04 | 3 | 99 |
| 2026-08 | past | 99 | 93.13 | 1 | 100 |
| 2026-09 | forward | 97.9 | 93.96 | 1.07 | 100 |
| 2026-10 | forward | 96.8 | 93.80 | 1.09 | 101 |
| 2026-11 | forward | 95.8 | 93.36 | 1.05 | 102 |
| 2026-12 | forward | 94.7 | 93.12 | 1.07 | 102 |
| 2027-01 | forward | 93.7 | 93.15 | 1.06 | 102 |
| 2027-02 | forward | 92.7 | 92.68 | 0.95 |  |
| 2027-03 | forward | 91.7 | 91.71 | 1.04 |  |
| 2027-04 | forward | 90.7 | 90.64 | 0.99 |  |
| 2027-05 | forward | 89.7 | 89.82 | 1.01 |  |
| 2027-06 | forward | 88.7 | 89.08 | 0.97 |  |
| 2027-07 | forward | 87.7 | 88.18 | 0.99 |  |
| 2027-08 | forward | 86.7 | 87.20 | 0.98 |  |

**Capacity projection, a diagnostic (diagnostic only: capacity was not adopted, so nothing in this report uses it):** bookings if capacity drove the forecast: rest of fiscal year $33,467,430; next twelve months $87,406,155; the forecast actually shown, at the flat rate: rest of fiscal year $33,191,902; next twelve months $85,003,210. Hiring action: unsupported by this history.

Limits:

- team_members.csv records no history of role, segment, quota or deal ownership: today's values stand in for every past date
- a deal's owner is its current owner, not necessarily the person who created it
- people who left the company before the first deal in the files are not on the roster

## 9. Quota against observed productivity

Wins credited to the owner on deals.csv and closed while that person was employed, over annual quota prorated by days employed in the window (trailing 365 days to 2026-08-31). Observed, never model output.

| Segment | Reps | Prorated quota | Wins credited | Attainment | Across reps employed 180+ days (min / p25 / median / p75 / max) |
|---|---|---|---|---|---|
| Enterprise | 56 | $55,374,247 | $29,408,150 | 53% | 0% / 0% / 0% / 100% / 366% |
| Mid-Market | 42 | $23,600,548 | $11,316,607 | 48% | 0% / 0% / 0% / 70% / 408% |
| Strategic Enterprise | 15 | $20,066,301 | $17,631,060 | 88% | 0% / 0% / 0% / 78% / 553% |
| all reps | 113 | $99,041,096 | $58,355,817 | 59% | 0% / 0% / 0% / 76% / 553% |

Wins in the window $62,591,952: credited $58,355,817, unattributed $4,236,135 (wins whose owner is not on the roster, or who had left or not yet started on the close date).

Total quota $109,200,000 for 99 people over a target of $84,000,000: **1.30x** (full-ramp annual quotas of the quota-carrying people employed on the as-of date (signed hires excluded) over the fiscal year's bookings target).

Limits:

- the owner is the deal's current owner and the quota is today's annual quota, standing in for their history
- quota is a full-ramp annual figure; ramp is not prorated out of it

## 10. Required against expected pipeline, by quarter

One deterministic solve in quarter order; each quarter's pipeline is created evenly on every day from the day after the as-of date to its end (creation starts now), and meets that quarter's target given its actual bookings, the pipeline already open and what earlier quarters were assigned; an unreachable quarter is assigned nothing. Pipeline assigned to a later quarter is also created in the earlier quarters' months, so it can only add to them. Forward function: the flat trailing rate. Cap: $2,390,337,558 (one cap across the quarters: three times the new-business pipeline created in the trailing 365 days, less what earlier quarters were assigned).

**The requirement.**

| Quarter | Target | Actual | Created between | Result | Cents booked in the quarter per dollar created | Bookings without own pipeline | Bookings under the completed schedule | Surplus over target |
|---|---|---|---|---|---|---|---|---|
| Q3FY26 | $22,000,000 | $2,440,779 | 2026-08-31 to 2026-10-31 | unreachable within the cap (it would take $6,609,519,382.53) | 0.10c | $15,239,945 | $15,446,388 | -$6,553,612 |
| Q4FY26 | $26,000,000 | $0 | 2026-08-31 to 2027-01-31 | required: $506,268,030.57 | 1.11c | $20,392,736 | $26,000,000 | $0 |

**Against the team's record.** Everything created in the span includes what earlier quarters were assigned.

| Quarter | Extra pipeline required | Expected created | Earlier quarters' assignments in the span | Total created in the span | Per day | Against the team's best per day | Per ramped AE-month (diagnostic, not the forecast's basis) | Against the team's best per ramped AE-month | Too late, and why |
|---|---|---|---|---|---|---|---|---|---|
| Q3FY26 | n/a | $138,674,657 | $0 | $6,748,194,039 | $110,626,132 | 48.98x | $35,866,134 | 42.52x (diagnostic) | too late: over_cap; total_rate |
| Q4FY26 | $506,268,031 | $347,823,319 | $0 | $854,091,350 | $5,582,296 | 2.47x | $1,817,675 | 2.16x (diagnostic) | too late: total_rate |

Too late, as a rule: a quarter is too late to fund with new pipeline when its requirement is over the cap (or the cap is used up, or no pipeline created in time can book inside it), or when everything created in its span (expected, earlier quarters' assignments and its own requirement) per day is above the team's best four-quarter average of total created pipeline per day, or, only where capacity is the forecast's basis, when that total per ramped AE-month is above the team's best; the reason names exactly the legs that fired. Per-ramped-AE-month comparison does not apply: capacity was not shown to explain pipeline in this history, so the per-ramped-AE-month comparison is a diagnostic only and does not decide; the cap and the total rate do.

Q3FY26: per ramped AE-month it would need $35,866,134, above the team's best of $843,465: a diagnostic here, it does not decide.

**Q3FY26: too late to fund with new pipeline: this quarter depends on the pipeline already open.** Why: the requirement is over the cap; needs $110,626,131.79 of pipeline created a day in total, above the team's best four-quarter average of $2,258,735.33 a day. The open pipeline ($201,970,221) is expected to book $12,657,333 inside the quarter; to close it, $19,417,388 of the open pipeline would have to book inside the quarter (9.6% of its dollars) against the 6.3% expected (arithmetic on the figures above, not a lever the model solves).

Q4FY26: per ramped AE-month it would need $1,817,675, above the team's best of $843,465: a diagnostic here, it does not decide.

**Q4FY26: too late to fund with new pipeline: this quarter depends on the pipeline already open.** Why: needs $5,582,296.40 of pipeline created a day in total, above the team's best four-quarter average of $2,258,735.33 a day. The open pipeline ($201,970,221) is expected to book $16,540,355 inside the quarter; to close it, $22,147,619 of the open pipeline would have to book inside the quarter (11.0% of its dollars) against the 8.2% expected (arithmetic on the figures above, not a lever the model solves).

**Lead time: of a dollar of pipeline created next month (at its first recorded amount), the cents booked by the end of each of the next four quarters** (created 2026-08-31 to 2026-09-30; the production forward function's own timing, on a probe dollar-amount created evenly through the month; independent of the capacity decision. These are dollar yields, not probabilities: amounts change between creation and win, so they can exceed or fall short of what the deal counts imply and are not forced to sum to one).

| Quarter | Cents booked inside the quarter | Cents booked by its end |
|---|---|---|
| Q3FY26 | 0.21c | 0.21c |
| Q4FY26 | 2.88c | 3.09c |
| Q1FY27 | 3.68c | 6.77c |
| Q2FY27 | 2.75c | 9.53c |
| After the fourth quarter | 0.10c |  |

Count outcome, of the deals created, from the fit in use; counts, so these sum to one: 9.1% expected to win within the horizon, 90.9% not.

Fiscal year, pipeline to meet every remaining quarter's target: **partial: 1 of 2 quarters solvable (unreachable: Q3FY26); $506,268,030.57 covers only the solvable ones; too late to fund with new pipeline: Q3FY26, Q4FY26**. Section 5's pipeline to meet the fiscal-year total, spread evenly to year end (section 5): feasible: $2,018,192,885.26. Meeting every quarter's own target is stricter than meeting the year's total: a quarter that is ahead cannot lend its surplus to one that is behind, and pipeline created in a quarter mostly books after it.

The team's own record (10 complete quarters, created pipeline dollars per ramped AE-month): median $806,071, best four-quarter average $843,465; best four-quarter average of total created pipeline $2,258,735 a day. Observed over the complete fiscal quarters in the files, with today's roster and ramp; fewer than four quarters has no four-quarter average.

_'required' means achievable inside the model's bounds (fitted conversion and timing, the cap above), not operationally achievable. Expected pipeline is what the forward function in use creates; the ramped AE-months beside it are the roster's expected ones (a diagnostic here: capacity was not adopted)._

## 11. The plan

Plan file `engine/config/profiles/mighty-oak-holdings/plan-program-only.yaml`. Hires first, then programs, each in the plan file's order; each contribution is the extra bookings from adding that item to everything above it, so they sum to the difference. Baseline: the roster as signed and nothing planned; the capacity term was not adopted, so hires are listed but not valued.

| Item | What |  | Adds, rest of fiscal year | Adds, next twelve months | Cash cost in twelve months |
|---|---|---|---|---|---|
| Channel partner program | $20,000,000 of created pipeline from 2026-10 | valued | $83,295 | $1,600,600 | $1,000,000 |

| Bookings | rest of fiscal year | next twelve months |
|---|---|---|
| Baseline | $33,191,901.81 | $85,003,210.23 |
| With the plan | $33,275,197.21 | $86,603,810.44 |
| Difference | $83,295.40 | $1,600,600.21 |
| Sum of the contributions | $83,295.40 | $1,600,600.21 |

Fiscal-year gap: $23,360,339 before the plan, **$23,277,044** with it (target $84,000,000, actual to date $27,447,759).

Twelve-month gap (against the quarters with a target that end in the window; later months are bookings alone): $12,367,319 before, **$12,284,024** with the plan.

Cash cost of the plan in the twelve months: $1,000,000 (hires at loaded cost per AE-month over expected months employed; programs at their cost, paid in step with the pipeline they create (or on the plan's own payment schedule), counting only what falls inside the twelve months).

Bookings with the plan, simulated (unvalidated: these ranges include the plan; they have not been back-tested; 2000 draws, drawing deal outcomes, with the planned hires and program pipeline in the scenario):

| Window | Median | 80% range | 95% range |
|---|---|---|---|
| rest of fiscal year | $32,754,783 | $21,921,675 to $45,416,896 | $17,888,517 to $54,565,056 |
| next twelve months | $86,149,250 | $65,932,283 to $108,785,720 | $57,341,414 to $122,708,233 |

Fiscal-year expected with the plan, 80% range: $49,369,434 to $72,864,654.

## 12. Two actions, compared

Two unit actions through the same forward function, the roster as signed: hire one AE starting 2026-09-01; add $1,000,000 of program pipeline starting 2026-09-01. Gain per dollar is the bookings gained in the next twelve months over the cash cost inside the same twelve months. An action starts paying in the first month it adds at least 1% of its twelve-month gain. Program shape: created from 2026-09 to the fiscal-year end, ramping up over the entered ramp (3 months unless capacity.yaml says otherwise).

| Action | Rank | Gains, rest of fiscal year | Gains, next twelve months | Starts paying | Cash cost inside the twelve months | Gain per dollar |
|---|---|---|---|---|---|---|
| Add $1,000,000 of program pipeline starting 2026-09-01 | 1 | $7,768 | $83,385 | 2026-12 | $50,000 | 1.67 |
| Hire one AE starting 2026-09-01 | unsupported by this history |  |  |  |  |  |

Closing the fiscal-year gap of $23,360,339: the baseline forecast (the roster as signed, nothing planned), each action alone.

- **Hires:** unsupported by this history: the hiring action is not valued, so there is no number of hires to solve for.
- **Program pipeline:** unreachable within the cap of $2,390,337,558 (the Goal 1 cap: three times the new-business pipeline created in the trailing 365 days); it would take $3,007,281,482.38.

_'feasible' means achievable inside the model's bounds, not operationally achievable; that a new hire adds pipeline at the fitted rate is an assumption._
