Minden hónap végén a legfrissebb CSV fájlok exportálásra kerülnek befoglalva térképről ([link](https://www.google.com/maps/d/viewer?mid=1hjOcx3VIAH9MZLk4EHSbGdCHQHe35R0), [link](https://offos.ch/befoglalva)) és feltöltésre kerülnek erre a repora. A commit neve tartalmazza, hogy melyik időpontról valók a fájlok.
A CSV fájlok mellett feltöltésre kerülnek a képek is az adott matricához.

A mappák neve a "Képek" mappában az adott layerhez tartoznak a Google mymaps-en. Egy adott kép neve pedig a koordináta ahol a kép készült (avagy ahova matrica ragasztva lett), majd utána szövegesen hogy hányadik kép, ha több kép készült ugyanarról a matricáról, amely megmondja, hogy a CSV fájlban az adott ponthoz hányadik dátumhoz tartozik a kép.

Példa:

Van 2 db kép egy koordinátához:
  - 46.14458, 18.15043, elso.png
  - 46.14458, 18.15043, masodik.png

A CSV fájlban a két koordináta fel van cserélve ahhoz képest ahogyan a térkép mutatja meg ahogy a googleben rá lehet keresni, plusz a CSV fájlban tárolt koordináta az sokszor "pontosabb", mint a kép nevében lévő koordináta, ezért érdemes a kép nevében lévő egyik koordináta alapján keresni a CSV fájlban.
CSV fájlban így néz ki egy pont:

&emsp;"POINT (18.150432 46.144588)",Orfű,Buci:\
&emsp;2023. 09. 18.?\
&emsp;Petaki:\
&emsp;2024. 06. 28.

Ehhez a koordinátához két dátum tartozik, így kettő kép is. Az első dátumhoz az "46.14458, 18.15043, elso.png" nevű kép, a második dátumhoz pedig a "46.14458, 18.15043, masodik.png" nevű kép tartozik.
