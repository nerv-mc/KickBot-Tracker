import asyncio
import httpx

RAW_DATA_TEXT = """
TJR $2
dcampion $2
kendace $2
duelbj $2
alyyy_xxx $2
blakjac21 $2
redwings944 $2
imbones $2
sangtar $2
coconutb $2
JtzCast $2
funnyhoodvidz $2
blonderabbit $2
keithlocks $2
Jamie $2
AverageAden $2
bigfoltz $2
frankdimes $2
BIGBOSSFF $2
Drago $2
auslots $2
cocospinzz $2
CUSTOMK $2
NeshyKing $2
ludopatos $2
Demize $2
GrayGray $2
Tyceno $2
LosPollosTV $2
CUSTOMK $2
Ryan6021 $2
Sav21 $2
DeMiZe $2
vasheeesh $2
classicnative $2
imbones $2
funnyhoodvidz $2
ClassyBeef $2
anthospins $2
wassimostv $2
ReachAces $2
keithlocks $2
lance $2
Bernie $2
runalong $2
Kukudota2 $2
scrapes $2
cocospinzz $2
berserk-cs2 $2
Doge $2
ADukes $2
DeMiZe $2
Gkbaby $2
Sangtar $2
Bigfoltz $2
Casiibro $2
kranzzofficial $2
starladder $2
starladder $2
mascoobs $2
AllonBlack1919 $2
theslotkiller $5
BlondeRabbit $5
slaeh $2
LosPollosTV $5
Tyceno $5
starladder $5
kingeen $2
starladder $5
JackpotMarki $2
Doge $5
GrayGray $5
starladder $5
starladder $5
starladder $5
starladder $5
Eddie $5
Eddie $5
Sav21 $5
DeMiZe $5
imbones $5
YungKarth $5
fastnslow $2
Lucky_girl13 $2
Schneckyirl $5
Locov2 $5
Syztmz $2
agony $5
CUSTOMK $5
sehamx $2
jaekcreates $2
dynamikyt $5
juke $5
cocospinzz $5
dcampion $5
novaneon $2
festIm $2
Hanvee $2
Doge $5
bath_dalts $2
Apploeninja $2
keithlocks $2
artybequacken $5
Classybeef $5
Bigfoltz $5
blakjac21 $5
wino87 $5
devorek $5
Tyceno $5
zombs $5
omie $5
BTCs $5
ChuckyBTZ $5
Eddie $5
Eddie $5
Eddie $5
gamblingjohn $5
ChuckyBTZ $5
Warren $2
LowLimit $2
Lance $5
newname $5
BTCs $5
Abstract $5
TCKGG $5
xwonn $5
Sneakzy $5
Bandz $5
nosedivegambles $5
mascoobs $5
Foss $5
CUSTOMK $5
BenDaDonnn $5
keithlocks $5
LosPollosTV $5
dcampion $5
realgafi $5
LeonNoLimit $5
TheRealPatty $5
Dosekai $5
abstract2 $2
imbones $5
DeMiZe $5
TJR $5
TheGoobr $5
schneckyirl $5
icesol $2
mintpod2 $5
jonjiponji $2
Zlatar $5
kingdodotv $5
water $5
reachaces $5
kyootbot $5
schlump $5
real_hyphonix $5
OVOPhantuums $2
Fornixtuned $2
daybeats $2
natankraken $5
Tyceno $5
Classybeef $5
GrayGray $5
haddzyjr $5
ramee $5
JackpotMarki $5
jackdoherty $5
sonecarox $5
katanatw $5
betwithkevin $5
shoovy $5
syzmool $5
moonlight2019 $5
magicaldota $5
cocospinzz $5
dcampion $5
ADukes $5
SiscoKid $5
dokkorki $5
dynamikyt $5
agony $5
ryda $5
ZombieBarricades $5
Prodigyddk $5
schneckyirl $5
iceinmyvein $5
Lance $5
bobmenery $5
DeMize $5
prophetgg $5
reachaces $5
remdog $5
vymzi $5
motivation $5
agony $5
Boltonbarbie $5
bakedalaska $5
jared $5
imbones $5
na5ty $5
BallySlots $5
Kranzzofficial $5
siscokid $5
xWonn $5
elglogloking $5
Sangtar $5
Lance $5
ladylotus $5
terriblepker $5
Real_Hyphonix $5
ihat3u $5
bath_dalts $5
LadyLuckSlots $5
DeMize $5
PezSlaps $5
TheDoctor $5
JaboleroHarhar $5
Shanrrr $5
cleanswipe $5
12amcupid $5
funnyhoodvidz $5
SlotsGuru $5
thehangmankick $5
vasheeesh $5
DDG $5
softypawz $5
bandz $5
oblivionsw $5
Doge $5
keithlocks $5
ChuckyBTZ $5
"""

API_ENDPOINT = "https://kickbot-tracker.online/api/v1/record-drop"

async def push_bulk_data():
    lines = [line.strip() for line in RAW_DATA_TEXT.strip().split("\n") if line.strip()]
    print(f"🚀 Memulai push {len(lines)} data histori ke sistem...")

    async with httpx.AsyncClient(timeout=10.0) as client:
        for index, line in enumerate(lines, start=1):
            parts = line.rsplit(" ", 1)
            if len(parts) == 2:
                streamer = parts[0].strip().lower()
                value = f"Kick Drop Event {parts[1].strip()}"
                
                payload = {
                    "streamer": streamer,
                    "value": value
                }

                try:
                    res = await client.post(API_ENDPOINT, json=payload)
                    if res.status_code == 200:
                        print(f"✅ [{index}/{len(lines)}] Success: {streamer} -> {parts[1]}")
                    else:
                        print(f"❌ [{index}/{len(lines)}] Failed: {streamer}")
                except Exception as e:
                    print(f"⚠️ Error {streamer}: {e}")
                
                await asyncio.sleep(0.2)

    print("\n🎉 PUSH DATA HISTORI SELESAI!")

if __name__ == "__main__":
    asyncio.run(push_bulk_data())
