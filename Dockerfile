FROM python:alpine

RUN pip3 install docker
RUN mkdir /hoster
WORKDIR /hoster
ADD hoster.py /hoster/

CMD ["python3", "-u", "hoster.py"]



