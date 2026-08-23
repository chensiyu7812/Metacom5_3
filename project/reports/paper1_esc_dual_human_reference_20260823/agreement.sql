WITH agreement(
  dimension_order,
  dimension,
  qwk,
  spearman,
  mad,
  exact_rate,
  major_disagreements
) AS (
  VALUES
    (1, 'Fluency',    0.6496350365, 0.6780784396, 0.6666666667, 0.5833333333, 4),
    (2, 'Expression', 0.8274111675, 0.8330153731, 0.3750000000, 0.7500000000, 2),
    (3, 'Empathy',    0.7641025641, 0.7870853825, 0.4583333333, 0.7500000000, 4),
    (4, 'Information',0.7720797721, 0.7652270470, 0.5833333333, 0.5416666667, 3),
    (5, 'Skillful',   0.7594936709, 0.7485322736, 0.5416666667, 0.5833333333, 3),
    (6, 'Humanoid',   0.7619047619, 0.7753910487, 0.7500000000, 0.2916666667, 1),
    (7, 'Overall',    0.7571428571, 0.8007370387, 0.6250000000, 0.4166666667, 1)
)
SELECT
  dimension_order,
  dimension,
  qwk,
  spearman,
  mad,
  exact_rate,
  major_disagreements
FROM agreement
ORDER BY dimension_order;
