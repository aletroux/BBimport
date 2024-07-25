#!/usr/bin/env python3
"""
Python code to convert question banks exported from Moodle in xml format into formats accepted by
Blackboard Ultra. 

@author: Alet Roux
@date: 23 July 2024

Command-line arguments:

  usage: %prog [options] filename 
    -h, --help            show this help message and exit

The output appears in the "output" subdirectory, in a separate file for each category and question type
(incorporated in the name of the file).

There are a few special cases:
- Descriptions are processed but cannot be imported into Blackbaord Ultra. They appear in files with names
containing the text "description".
- The xml (converted to dictionary text) for unsupported question types are collected in files with names
containing the text *unsupported*.
- Questions where there were errors are collected in files with names containing the text *malformed*.

"""

from dataclasses import dataclass
import re
import sys

# for command line arguments
import argparse

# open files
import pathlib
import base64

# Extract Moodle questions
import xmltodict

@dataclass
class Question:
    question: str
    files: list[tuple[str,str]] # filenames and their (binary) contents

    # initiates from Moodle (in dict format)
    def __init__(self, Moodle_question):
        self.question = self._cleanstring(Moodle_question["questiontext"]["text"], format = Moodle_question["questiontext"]["@format"])
        self.files = []
        
        # if the question has a file attached.
        # please note that a question can have multiple files attached, and there is no way of telling where these files are linked in the question.
        # for this reason, all files are referred to in the question text.
        if "file" in Moodle_question["questiontext"]:
            # first ensure we have a list of files
            if isinstance(Moodle_question["questiontext"]["file"], list):
                files = Moodle_question["questiontext"]["file"]
            else:
                files = [ Moodle_question["questiontext"]["file"] ]

            # encode each file and make a note in the question
            for file in files:
                if file["@encoding"] == "base64":
                    self.files.append( (file["@name"], base64.b64decode(file['#text'], validate=True)) )

                self.question += " [[ linked file " + file["@name"] + " ]]"
    
    def _cleanstring (self, input, format = 'html'):
        """Cleans text before converting. The contents of this function is ad-hoc and definitely a work in progress - feel free to adjust to taste"""

        if input is None:
            return ""

        if format == 'html':
            # remove leading and trailing whitespace, as well as newlines (not allowed in Blackboard Ultra)
            output = ''.join(input.split('\n'))

            # replace pairs of single dollar signs with double dollars (used to denote LaTeX in BB Ultra)
            output = re.sub(r"\$(.*?)\$", lambda s : '$$' + s.group(1) + '$$', output)

            # replace pairs of \( \) and \[ \] with double dollars (used to denote LaTeX in BB Ultra)
            output = re.sub(r"\\\((.*?)\\\)", lambda s : '$$' + s.group(1) + '$$', output)
            output = re.sub(r"\\\[(.*?)\\\]", lambda s : '$$' + s.group(1) + '$$', output)

            # now for html parsing / simplification

            # remove paragraph formatting
            output = re.sub(r"<p .*?>", '<p>', output)           

            # remove span formatting
            
            # remove breaks at start and end of string
            
            # remove empty paragraphs
            output = re.sub("<p></p>", "", output)

            #use breaks instead of paragraphs

        elif format == "moodle_auto_format":
            #very basic format, basically raw text though it can contain a single equation

            # replace pairs of single dollar signs with double dollars (used to denote LaTeX in BB Ultra)
            output = re.sub(r"^\$(.*?)\$$", lambda s : '$$' + s.group(1) + '$$', input)

        else:
            print ("chosen format", format, "hasn't been implemented for string", input)
            output = input

        return output

    # returns "question" text
    def to_BBultra (self):
        return self.question

    # writes contents of files
    def writefiles (self, rootname):
        for file in self.files:
            f = open(rootname + "_" + file[0], 'wb')
            f.write(file[1])
            f.close()

@dataclass
class Description(Question):
    """Description: not a question type in Blackboard Ultra but nonetheless recorded"""

    # initiates from Moodle (in dict format)
    def __init__(self, Moodle_question):
        super().__init__(Moodle_question)

@dataclass
class Malformed(Question):
    """Records xml of malformed questions"""

    # initiates from Moodle (in dict format)
    def __init__(self, Moodle_question):
        self.question = str(Moodle_question)
        self.files = []

@dataclass
class Matching(Question):
    """Matching type question ('matching' in Moodle, 'MAT' in Blackboard Ultra)"""
    
    answers: list[tuple[str,str]] # pairs of answers

    #initiates from Moodle (in dict format)
    #negative grades not allowed
    def __init__(self, Moodle_question):
        super().__init__(Moodle_question)
        self.answers = [(self._cleanstring(subquestion["text"], subquestion["@format"]), self._cleanstring(subquestion["answer"]["text"], subquestion["@format"])) for subquestion in Moodle_question["subquestion"]] 

    def to_BBultra (self):
        line = "MAT\t" + self.question
        for answer1,answer2 in self.answers:
            line += "\t" + answer1 + "\t" + answer2
        return line

@dataclass
class MultiChoice(Question):
    """Multiple choice question ('multichoice' in Moodle, 'MC' in Blackboard Ultra)"""
    
    answers: list[tuple[str,str]] # pairs of (answer, "correct" or "incorrect")

    #initiates from Moodle (in dict format)
    #negative grades not allowed
    def __init__(self, Moodle_question):
        super().__init__(Moodle_question)
        self.answers = [(self._cleanstring(answer["text"], answer["@format"]), "correct" if float(answer["@fraction"]) > 0 else "incorrect") for answer in Moodle_question["answer"]] 

    def to_BBultra (self):
        line = "MC\t" + self.question
        for answer,result in self.answers:
            line += "\t" + answer + "\t" + result
        return line

@dataclass
class Essay(Question):
    """Essay type question ('essay' in Moodle, 'ESS' in Blackboard Ultra)"""

    generalfeedback: str # general feedback (e.g. model solution)
    graderinfo: str # info for grader (e.g. mark scheme)

    #initiates from Moodle (in dict format)
    def __init__(self, Moodle_question):
        super().__init__(Moodle_question)
        self.generalfeedback = self._cleanstring(Moodle_question["generalfeedback"]["text"], Moodle_question["generalfeedback"]["@format"]) 
        self.graderinfo = self._cleanstring(Moodle_question["graderinfo"]["text"], Moodle_question["graderinfo"]["@format"]) 

    def to_BBultra (self, graderinfo = True):
        line = "ESS\t" + self.question 
        if len(self.generalfeedback) > 0:
            line += "\t" + self.generalfeedback
        if len(self.graderinfo) > 0:
            line += "\t" + self.graderinfo
        return line

@dataclass
class Cloze(Question):
    """Fill in the blanks question ('cloze' in Moodle, 'FIB_PLUS' in Blackboard Ultra)"""

    answers: list[tuple[str,str]] # pairs of (placeholder, answer)
    variables = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]

    #initiates from Moodle (in dict format)
    def __init__(self, Moodle_question):
        super().__init__(Moodle_question)
        self.answers = []

        # need to remove all square brackets '[' and ']' from the question as they cause issues in Blackboard.
        self.question = self.question.replace("[",r"$$\lbrack$$")
        self.question = self.question.replace("]",r"$$\rbrack$$")

        # each candidate answer is of the form {mark:type:answers} where the correct answer is preceeded by an '=' and 
        # (if not at end) preceeds a '#' or a '~' irrespective of the type of answer.
        candidates = re.findall(r"\{(.*?)\}", self.question)
        for match in candidates:
            answer = match.split(":")[2].split('=')[1].split('~')[0].split('#')[0]
            variable = self.variables[len(self.answers)]
            self.answers.append( (variable, answer) )
            self.question = self.question.replace("{" + match + "}","[" + variable + "]")

    def to_BBultra (self, graderinfo = True):
        if len(self.answers) > 1:
            line = "FIB_PLUS\t" + self.question
            for variable,answer in self.answers:
                 line += "\t" + variable + "\t" + answer + "\t"
        else:
            line = "FIB\t" + self.question + "\t" + answer[0][0]
            
        return line

@dataclass
class ShortAnswer(Question):
    """Short answer question ('shortanswer' in Moodle, 'FIB' in Blackboard Ultra)"""

    answers: list[str] # list of answers

    #initiates from Moodle (in dict format)
    def __init__(self, Moodle_question):
        super().__init__(Moodle_question)

        # need to remove all square brackets '[' and ']' from the question as they cause issues in Blackboard.
        self.question = self.question.replace("[",r"$$\lbrack$$")
        self.question = self.question.replace("]",r"$$\rbrack$$")

        self.answers = []

        # turn answers into list for code efficiency (sometimes it's a list, sometimes not)
        if isinstance(Moodle_question["answer"], list):
            answers = Moodle_question["answer"]
        else:
            answers = [ Moodle_question["answer"] ]
            
        for answer in answers:
            if int(answer['@fraction']) == 100:
                self.answers.append(self._cleanstring(answer["text"], answer["@format"]))

    def to_BBultra (self, graderinfo = True):
        line = "FIB\t" + self.question + " [a]"
        for answer in self.answers:
            line += "\t" + answer
        return line

@dataclass
class TrueFalse(Question):
    """Short answer question ('truefalse' in Moodle, 'TF' in Blackboard Ultra)"""

    answer: str
    
    #initiates from Moodle (in dict format)
    def __init__(self, Moodle_question):
        super().__init__(Moodle_question)

        # turn answers into list for code efficiency (sometimes it's a list, sometimes not)
        if isinstance(Moodle_question["answer"], list):
            answers = Moodle_question["answer"]
        else:
            answers = [ Moodle_question["answer"] ]

        for answer in answers:
            if int(answer['@fraction']) == 100:
                self.answer = self._cleanstring(answer["text"], answer["@format"])

    def to_BBultra (self, graderinfo = True):
        line = "TF\t" + self.question + "\t" + self.answer
        return line

@dataclass
class Numerical(Question):
    """Numerical type question ('numerical' in Moodle, 'NUM' in Blackboard Ultra)"""

    answer: str
    tolerance: str

    #initiates from Moodle (in dict format)
    def __init__(self, Moodle_question):
        super().__init__(Moodle_question)
        
        # turn answers into list for code efficiency (sometimes it's a list, sometimes not)
        if isinstance(Moodle_question["answer"], list):
            answers = Moodle_question["answer"]
        else:
            answers = [ Moodle_question["answer"] ]

        for answer in answers:
            if int(answer['@fraction']) == 100:
                self.answer = self._cleanstring(answer["text"], answer["@format"])
                self.tolerance = self._cleanstring(answer["tolerance"], answer["@format"])
            
    def to_BBultra (self, graderinfo = True):
        return "NUM\t" + self.question + "\t" + self.answer + "\t" + self.tolerance

def parseArguments():
    # Create argument parser
    parser = argparse.ArgumentParser()
    
    # Positional mandatory arguments
    parser.add_argument("filename", help="name of xml file with Moodle quiz questions", type=str)
     
    # Parse arguments
    args = parser.parse_args()
    
    return args

def write_questions_to_file (questions, category, dirname):
    """saves all questions in this category to file in the directory dirname
    questions are grouped by type of question"""
    print(f"\nCategory {category}:")
    for qtype in questions:
        print(f"\t{len(questions[qtype])} questions of type {qtype}")
        rootname = dirname + category.replace("/","_") + "_" + qtype
        
        output = ""
        for question in questions[qtype]:
            output += question.to_BBultra() + "\n"
            question.writefiles (rootname)
    
        file = pathlib.Path(rootname + ".txt")
        file.write_text(output)

def main(arguments):

    # open xml file
    filename = arguments.filename
    text = pathlib.Path(filename).read_text()

    # put all files in "output/" subdirectory
    dirname = "output/"
    p = pathlib.Path("output")
    p.mkdir(parents=True, exist_ok = True)

    # convert xml to dict - the "quiz" entry contains the list of questions
    dict = xmltodict.parse(text)
    dict = dict["quiz"]["question"]

    # a dict of all question types - will be collected by type and saved to file by category as part of the process
    questions = {}

    # starting value
    category = None

    for question in dict:
        try:
            if question["@type"] == "category":
                #it's not a question, it's a category identifier
                #all questions following this 'question' fall in this category
                
                # write lists of questions and descriptions of previous category to file
                if not category is None:
                    write_questions_to_file (questions, category, dirname)
                    questions = {}
        
                category = question["category"]["text"]
        
                # remove top signifier if it's present
                category = category.replace("$course$/top/","")
        
            elif question["@type"] == "cloze":
                q = Cloze(question)
                if not "cloze" in questions:
                    questions["cloze"] = []
                questions["cloze"].append(q)
                
            elif question["@type"] == "description":
                q = Description(question)
                if not "description" in questions:
                    questions["description"] = []
                questions["description"].append(q)
                
            elif question["@type"] == "essay": 
                q = Essay(question)
                if not "essay" in questions:
                    questions["essay"] = []
                questions["essay"].append(q)
                
            elif question["@type"] == "matching": 
                q = Matching(question)
                if not "matching" in questions:
                    questions["matching"] = []
                questions["matching"].append(q)
                
            elif question["@type"] == "multichoice":
                q = MultiChoice(question)
                if not "multichoice" in questions:
                    questions["multichoice"] = []
                questions["multichoice"].append(q)
        
            elif question["@type"] == "numerical":
                #print(question)
                q = Numerical(question)
                if not "numerical" in questions:
                    questions["numerical"] = []
                questions["numerical"].append(q)
        
            elif question["@type"] == "shortanswer":
                q = ShortAnswer(question)
                if not "shortanswer" in questions:
                    questions["shortanswer"] = []
                questions["shortanswer"].append(q)
        
            elif question["@type"] == "truefalse":
                q = TrueFalse(question)
                if not "truefalse" in questions:
                    questions["truefalse"] = []
                questions["truefalse"].append(q)
        
            else:
                q = Malformed(question)
                if not "*unsupported*" in questions:
                    questions["*unsupported*"] = []
                questions["*unsupported*"].append(q)
        except:
            if not "*malformed*" in questions:
                questions["*malformed*"] = []
            questions["*malformed*"].append(Malformed(question))
            
    
    # write questions of final category
    write_questions_to_file (questions, category, dirname)

# main script
if __name__ == '__main__':
    # Parse the arguments
    args = parseArguments()

    # Message
    print("\nMoodle to Blackboard Ultra quiz converter")
    print("=========================================")

    # Run function
    main(args)
    sys.exit(0)   