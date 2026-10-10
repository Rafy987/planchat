# Evaluation results

Run on 2026-10-10 with `qwen/qwen3.8-27b` (Groq), top_k=5, chunk size 800/150. Took 254 s. Re-run with `python -m evaluation.run`.

| | Hybrid search (used by the app) | Vector search only |
|---|---|---|
| Answer correct | **100% (20/20)** | 90% (18/20) |
| Cites the right page | **100% (20/20)** | 100% (20/20) |
| Right page found by search | **100% (17/17)** | 100% (17/17) |

| Flooring schedule extractor | Score |
|---|---|
| Product codes found | **100% (14/14)** |
| Correct category (of found) | 100% (14/14) |
| Exactly the right rooms (of found) | 100% (14/14) |
| Extra codes that shouldn't be there | 0  |

## Questions: hybrid search

| # | Question | Answer | Cites page | Search hit | Answer given | Why wrong |
|---|---|---|---|---|---|---|
| 1 | What flooring is in Exam 1? | ✅ | ✅ | ✅ | The flooring in Exam 1 (Room 104) is SV-1, which is Sheet Vinyl: Armstrong, 'Medintone', heat welded seams, color Slate [p. 3] [p. 4]. |  |
| 2 | What is the floor finish in the waiting room? | ✅ | ✅ | ✅ | The floor finish in the waiting room (Room 101) is CPT-1 [p. 3]. |  |
| 3 | What base is used in the toilet room? | ✅ | ✅ | ✅ | The toilet room (Room 106) uses base **PT-1B** [p. 3]. According to the finish legend, PT-1B is a **Porcelain Tile Base** by Daltile, 6" cove to match PT-1 [p.… |  |
| 4 | What is the ceiling in the storage room? | ✅ | ✅ | ✅ | The ceiling in the storage room (Room 108) is EXPOSED [p. 3]. |  |
| 5 | Who manufactures LVP-1? | ✅ | ✅ | ✅ | Tarkett [p. 4] |  |
| 6 | What color is the sheet vinyl SV-1? | ✅ | ✅ | ✅ | The sheet vinyl SV-1 is color slate [p. 4]. |  |
| 7 | How long is the warranty for the resilient flooring? | ✅ | ✅ | ✅ | The warranty for the resilient flooring is a manufacturer's 10-year limited warranty [p. 5]. |  |
| 8 | Which rooms have resilient flooring? | ✅ | ✅ | ✅ | Based on the Room Finish Schedule [p. 3] and the Finish Legend [p. 4], the rooms with resilient flooring (LVP-1, SV-1, VCT-1) are: * **102 RECEPTION** (LVP-1) … |  |
| 9 | Which rooms use RB-2 base? | ✅ | ✅ | ✅ | Rooms 104 (EXAM 1) and 105 (EXAM 2) use RB-2 base [p. 3]. |  |
| 10 | Which rooms have luxury vinyl plank? | ✅ | ✅ | ✅ | Based on the Room Finish Schedule [p. 3], the rooms with luxury vinyl plank (LVP-1) are: * 102 RECEPTION * 103 CORRIDOR * 107 STAFF LOUNGE |  |
| 11 | What is the outlet size of the roof drains? | ✅ | ✅ | ✅ | The roof drains have a 4 inch outlet [p. 6]. |  |
| 12 | What is the fire rating of the corridor walls? | ✅ | ✅ | – | I couldn't find that in the document. |  |
| 13 | What flooring is in the reading room? | ✅ | ✅ | ✅ | The reading room (Room 101) has CPT-1 flooring [p. 6]. CPT-1 is Mohawk Group, 'Lasting Mark', 24 x 24 in, color graphite [p. 3]. |  |
| 14 | Who makes CPT-1? | ✅ | ✅ | ✅ | CPT-1 is made by Mohawk Group [p. 3]. |  |
| 15 | What grout is specified for the porcelain tile? | ✅ | ✅ | ✅ | Laticrete Spectralock Pro epoxy grout [p. 4]. |  |
| 16 | What is the warranty on the resilient tile flooring? | ✅ | ✅ | ✅ | The resilient tile flooring has a 15-year manufacturer's warranty [p. 2]. |  |
| 17 | What door closers are specified? | ✅ | ✅ | ✅ | LCN 4040XP, surface mounted [p. 5]. |  |
| 18 | Which rooms have carpet? | ✅ | ✅ | ✅ | Based on the Room Finish Schedule, the rooms with carpet (CPT) are: * 101 READING ROOM (CPT-1) [p. 6] * 104 ENTRY VESTIBULE (CPT-2) [p. 6] |  |
| 19 | What roof membrane is specified? | ✅ | ✅ | – | I couldn't find that in the document. |  |
| 20 | Which brand of toilet partitions is specified? | ✅ | ✅ | – | I couldn't find that in the document. |  |

## Questions: vector search only

| # | Question | Answer | Cites page | Search hit | Answer given | Why wrong |
|---|---|---|---|---|---|---|
| 1 | What flooring is in Exam 1? | ✅ | ✅ | ✅ | The flooring in Exam 1 (Room 104) is SV-1, which is Sheet Vinyl: Armstrong, 'Medintone', heat welded seams, color Slate [p. 3] [p. 4]. |  |
| 2 | What is the floor finish in the waiting room? | ✅ | ✅ | ✅ | The floor finish in the waiting room (Room 101) is CPT-1 [p. 3]. |  |
| 3 | What base is used in the toilet room? | ✅ | ✅ | ✅ | The toilet room (Room 106) uses base PT-1B [p. 3]. |  |
| 4 | What is the ceiling in the storage room? | ✅ | ✅ | ✅ | The ceiling in the storage room (Room 108) is EXPOSED [p. 3]. |  |
| 5 | Who manufactures LVP-1? | ✅ | ✅ | ✅ | Tarkett [p. 4]. |  |
| 6 | What color is the sheet vinyl SV-1? | ✅ | ✅ | ✅ | The sheet vinyl SV-1 is color slate [p. 4]. |  |
| 7 | How long is the warranty for the resilient flooring? | ✅ | ✅ | ✅ | The warranty for the resilient flooring is a manufacturer's 10-year limited warranty [p. 5]. |  |
| 8 | Which rooms have resilient flooring? | ❌ | ✅ | ✅ | Based on the Room Finish Schedule [p. 3] and the specification for Resilient Tile Flooring [p. 5], the rooms with resilient flooring (LVP-1 or VCT-1) are: * 10… | missing 104, 105 |
| 9 | Which rooms use RB-2 base? | ✅ | ✅ | ✅ | Rooms 104 (EXAM 1) and 105 (EXAM 2) use RB-2 base [p. 3]. |  |
| 10 | Which rooms have luxury vinyl plank? | ❌ | ✅ | ✅ | Rooms 102 (Reception) and 107 (Staff Lounge) [p. 3]. | missing 103 |
| 11 | What is the outlet size of the roof drains? | ✅ | ✅ | ✅ | The roof drains have a 4 inch outlet [p. 6]. |  |
| 12 | What is the fire rating of the corridor walls? | ✅ | ✅ | – | I couldn't find that in the document. |  |
| 13 | What flooring is in the reading room? | ✅ | ✅ | ✅ | The reading room (Room 101) has CPT-1 flooring [p. 6]. CPT-1 is Mohawk Group, 'Lasting Mark', 24 x 24 in, color graphite [p. 3]. |  |
| 14 | Who makes CPT-1? | ✅ | ✅ | ✅ | Mohawk Group [p. 3]. |  |
| 15 | What grout is specified for the porcelain tile? | ✅ | ✅ | ✅ | Laticrete Spectralock Pro epoxy grout [p. 4]. |  |
| 16 | What is the warranty on the resilient tile flooring? | ✅ | ✅ | ✅ | The resilient tile flooring has a 15-year manufacturer's warranty [p. 2]. |  |
| 17 | What door closers are specified? | ✅ | ✅ | ✅ | LCN 4040XP, surface mounted [p. 5]. |  |
| 18 | Which rooms have carpet? | ✅ | ✅ | ✅ | Based on the Room Finish Schedule, the rooms with carpet (CPT) are: * 101 READING ROOM (CPT-1) [p. 6] * 104 ENTRY VESTIBULE (CPT-2) [p. 6] |  |
| 19 | What roof membrane is specified? | ✅ | ✅ | – | I couldn't find that in the document. |  |
| 20 | Which brand of toilet partitions is specified? | ✅ | ✅ | – | I couldn't find that in the document. |  |

## Flooring extractor details

- **clinic**: found 9/9, missed none, extra none, right category 9, right rooms 9
- **library**: found 5/5, missed none, extra none, right category 5, right rooms 5
