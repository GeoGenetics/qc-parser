
# NF assesment
## 1. Single-table inheritance

Note: key means natural candidate key. It can be composite. 
Attribute dependency = if one is changed the other also needs to be changes, otherwise inconsistencies will happen.

### 1NF
For each table:
Does every column contain one value of one type? Yes
Are lists, arrays, comma-separated values, or repeating columns such as mineral_1, mineral_2 being used? No
Does every row have a candidate key? yes
Conclusion: 1NF obtained

### 2NF
Is 1NF obtained: Yes
For every table:
For every non-key attribute:
If the key is composite, does an attribute depend on only one part of it? No
Would updating one row require updating multiple rows? no
Does updating a fact require updating multiple rows? Example fact: Sample A was sampled in Greenland. NO
Are all non-key attributes a property/attribute of the "entity" that the primary key is identifying? In other words: Is each non-key attributes associated with the entire primary key? yes
Conclusion: 2nf obtained

General Example: in (sample_id, analysis_type_id, analysis_type_name), analysis_type_name depends only on analysis_type_id and belongs elsewhere.

### 3NF
Is 2NF obtained: YES
For each candidate key:
Does every non-key attribute depend on the key and nothing but the key? I.e. not on other non-key attributes? YES
Can updating a non-key attribute result in another non-key attribute to become invalid? NO except depth interval but that is in essence a single attribute. 
Conclusion: 3NF obtained.

### BCNF:
Is 3NF obtained? YES
Does all attributes depend on nothing but the primary natural key? I.e. not on other non-key attributes? 
Can updating any attribute result in another attribute to become invalid?


### 4NF 
Is BCNF obtained: YES
Is there more than 1 one to many relationships from one attribute to another an are those attributes unrelated? Example if a table contains course ID, textbooks and lecturers and they form a composite key.  A single course can contain many textbooks and there can be many lecturers. But textbook and lecturer is unrelated. There might be 10 textbooks but only 2 lecturers. If a lecturer is replaced, textbooks does not necessarily change. NO
Conclusion: 4NF obtained

### 5NF
is 4nf obtained: YES
Does the table represent an association among three or more entities? NO
Conclusion: 5NF obtaineed

## 2. One table per sample type

Attribute dependency = if one is changed the other also needs to be changes, otherwise inconsistencies will happen.

### 1NF
For each table:
Does every column contain one value of one type? Yes
Are lists or arrays or, comma-separated values used? No
Are  repeating columns such as mineral_1, mineral_2 being used? No
Does every row have a candidate key? yes
Conclusion: 1NF obtained

### 2NF
Is 1NF obtained: YYES
For every table:
For every non-key attribute:
Do any table have a composite key? NO. If yes does any attribute depend on only one part of it? 
Would updating one row require updating multiple rows? NO
Are all non-key attributes a property/attribute of the "entity" that the primary key is identifying? yes
Conclusion: 2nf obtained

General Example: in (sample_id, analysis_type_id, analysis_type_name), analysis_type_name depends only on analysis_type_id and belongs elsewhere.

### 3NF
Is 2NF obtained: YES
For each candidate key:
Does every non-key attribute depend on the key and nothing but the key? I.e. not on other non-key attributes? YES
Can updating a non-key attribute result in another non-key attribute to become invalid? NO. 
Conclusion: 3NF obtained.

### BCNF (only relevant if there are composite keys):
Is 3NF obtained? YES 
Does updating a key attribute result in another key attribute becoming invalid? NO

### 4NF 
Is BCNF obtained: YES
Are there more than 1 one-to-many relationships from one attribute to another and are those attributes unrelated? Example if a table contains course ID, textbooks and lecturers and they form a composite key.  A single course can contain many textbooks and there can be many lecturers. But textbook and lecturer is unrelated. There might be 10 textbooks but only 2 lecturers. If a lecturer is replaced, textbooks does not necessarily change. NO
Conclusion: 4NF obtained

### 5NF
is 4nf obtained: YES
Does the table represent an association among three or more entities? NO
Conclusion: 5NF obtaineed