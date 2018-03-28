#docker build -t ronhanson/jobmanager-builder .

docker run --rm -ti --name jobmanager-builder -p 5001:5001 -v /private/var/run/docker.sock:/private/var/run/docker.sock ronhanson/jobmanager-builder $* 
