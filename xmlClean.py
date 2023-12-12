import fnmatch
import sys
from contrabandCheckSettings import contrabandIds

#Get arguments
xmlFileName = sys.argv[1]
accountNum = sys.argv[2]


#Get the xml file line
file = open(xmlFileName, "r")

xmlFileData = file.readline()

file.close()

#Remove all the items
for item in contrabandIds:

    #Find the index where the item entry starts
    startIndex = xmlFileData.find('<i l="' + str(item["id"]) + '"')
    
    #Only continue if the item was found
    if startIndex != -1:
        print("Item " + str(item["id"]) + ", match!")
    
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
