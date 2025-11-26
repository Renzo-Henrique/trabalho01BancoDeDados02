all:
	docker stop $(docker container ls -aq)
	docker rm $(docker container ls -aq)
	docker volume rm -f $(docker volume ls -q)
	docker image prune -a -f