import fnmatch
import sys

#Get arguments
xmlFileName = sys.argv[1]
accountNum = sys.argv[2]

#Items to remove
itemNums = [
    14128,
    6655,
    9947,
    9948,
    9949,
    7791,
    12305,
    13779,
    13101,
    10155,
    13302,
    12886,
    13912,
    13913,
    13911,
    13917,
    2988,
    5674,
    12100,
    3849,
    10476,
    11293,
    13312,
    10156,
    10053,
    8600,
    8359,
    8605,
    10130,
    12792,
    12793,
    12667,
    14571,
    7641,
    10430,
    14191,
    14560,
    14561,
    14559,
    14194,
    14569,
    14568,
    14570,
    14192,
    14562,
    14563,
    14564,
    14193,
    14802,
    8535,
    12099,
    15918,
    15989,
    16123,
    14803,
    13923,
    13919,
    13921,
    14107,
    13918,
    13922,
    12774,
    14109,
    14108,
    10154,
    10054,
    13309,
    8519,
    8080,
    12450,
    1727,
    13276,
    13278,
    13275,
    13277 ]

#Get the xml file line
file = open(xmlFileName, "r")

xmlFileData = file.readline()

file.close()

#Remove all the items
for item in itemNums:

    #Find the index where the item entry starts
    startIndex = xmlFileData.find('<i l="' + str(item) + '"')
    
    #Only continue if the item was found
    if startIndex != -1:
        print("Item " + str(item) + ", match!")
    
        index = startIndex

        #Find the index where the item entry stops
        while xmlFileData[index] != ">":
            index += 1
            
            #error if we for some reason reach the end of array index
            if index >= len(xmlFileData):
                sys.exit("Index grew larger than file index")
                
        endIndex = index + 1

        #print(xmlFileData[startIndex:endIndex])

        #Remove the item
        xmlFileData = xmlFileData.replace(xmlFileData[startIndex:endIndex], "")

        #print(xmlFileData[startIndex:endIndex])
    else:
        pass
        #print("Item " + str(item) + ", no match")


#Update account number

#Find the index where the entry starts
startIndex = xmlFileData.find('<char acct=')

index = startIndex 
quoteCount = 0

#Find the index where the entry stops
while quoteCount != 2:
    #Count the number of time we reached a "
    if xmlFileData[index] == '"':
        quoteCount += 1
    
    index += 1
    
    #error if we for some reason reach the end of array index
    if index >= len(xmlFileData):
        sys.exit("Index grew larger than file index")
        

        
endIndex = index + 1


#print(xmlFileData[startIndex:endIndex])

#Replace with new account number
xmlFileData = xmlFileData.replace(xmlFileData[startIndex:endIndex], '<char acct="' + str(accountNum) + '" ')

#print(xmlFileData[startIndex:endIndex])

#Write back the file
file = open(xmlFileName, "w")

file.write(xmlFileData)

file.close()

print("Done")
