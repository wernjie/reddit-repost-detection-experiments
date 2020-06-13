#!/usr/bin/env python3

from PIL import Image
import pytesseract

class OCR:

    def __init__(self):
        pass

    @staticmethod
    def read(meme, original: bool = False):
        '''Reads the image directly using pytesseract, unedited, and returns the text result.

        By default, returned string has no newlines and has one space between all words.
        Dashes followed by newlines are removed and the word is merged properly.

        To get the raw output, set the original parameter to True.
        '''
        rawtext = pytesseract.image_to_string(meme)
        if original:
            return rawtext
        rawtext = rawtext.replace("-\n", "")
        nlsplit = rawtext.split("\n")
        final = ""
        for i in nlsplit:
            edit = i.split(" ")
            newstring = ""
            for g in edit:
                if g != "":
                    newstring = newstring + g + " "
            final = final + newstring


        return final

if __name__ == "main.py":
    ocr = OCR
    print(ocr.read("potato.jpg"))
