(function($){

    var socket = io('http://' + document.domain + ':' + location.port, {transports: ['websocket']});
    socket.on('connect', function() {

        function on_progress_message(data) {
            console.log(data.message);
            var old = $("#loading label").html();
            var new_div = $("<small>"+old+"</small>");
            $("#loading label").html(data.message).slideDown();
            new_div.hide();
            $("#loading label").after(new_div);
            new_div.slideDown();
            $("#loading small").each(function(i, el) {
                $(el).css("opacity", $(el).css("opacity")*0.60);
            });
            $("#debug").val($("#debug").val() + '\n' + data.message);
            console.log("DEBUG - " + data.message);
        }

        socket.off('progress message');
        socket.on('progress message', on_progress_message);

        function on_debug_message(data) {
            $("#debug").val($("#debug").val() + '\n' + data.message);
            console.log("DEBUG - " + data.message);
        }

        socket.off('debug message');
        socket.on('debug message', on_debug_message);
    });

    $('input.tag').tagEditor({delimiter:' '});

    $('.fileinput').each(function(i, input){
        var label	 = input.nextElementSibling,
            labelVal = label.innerHTML;

        $(input).on('change', function(e) {
            var fileName = e.target.value.split( '\\' ).pop().split( '/' ).pop();

            if( fileName ) { label.querySelector( 'span' ).innerHTML = fileName; }
        });
    });

    $('#submit').on('click', function(e) {
        var formData = new FormData(document.querySelector('form#builder'));

        if (on_build_submit) {
            formData = on_build_submit(formData, socket);
        }

        if ($('form#builder')[0].checkValidity()) {
            $("#loading label").html('Please wait, this might take a while...');
            $("#loading small").remove();
            $("#debug").val('');

            $('#builder').hide();
            $('#loading').show();

            axios.post('/build', formData).then(function (response) {
                $('#result #message').html(response.data.message.replace('\n', '<br/>'));
                $('#result #details').val(response.data.details);
                if (response.data.result == "success") {
                    $('#result #image').show();
                    $('#result #jobs').show();

                    $('#result i.big').removeClass('fa-exclamation-circle error').addClass('fa-check-circle success');

                    // Image
                    $('#result #image').html(response.data.uuid);

                    // Tags
                    $('#result #tags').html('');
                    _.each(response.data.tags, function(t) {
                        var tag = $("<div class='tag emboss'/>").html(t);
                        $('#result #tags').append(tag);
                    });

                    // Jobs
                    $('#result #jobs').html('<label>This image will be able to execute the following jobs : </label>');
                    _.each(response.data.jobs, function(j) {
                        var job = $("<div class='job'/>").html(j);
                        $('#result #jobs').append(job);
                    });

                    // Tasks
                    if (response.data.tasks.length>0) {
                        $('#result #tasks').html('<label>And following sub tasks:</label>');
                        _.each(response.data.tasks, function(j) {
                            var task = $("<div class='tasks'/>").html(j);
                            $('#result #tasks').append(task);
                        });
                    }

                } else {
                    $('#result #image').hide();
                    $('#result #jobs').hide();
                    $('#result i.big').removeClass('fa-check-circle success').addClass('fa-exclamation-circle error');
                }
            }).catch(function(error) {
                    $('#result #image').hide();
                    $('#result #jobs').hide();
                    $('#result #message').html("Critical error during build request");
                    $('#result i.big').removeClass('fa-check-circle success').addClass('fa-exclamation-circle error');
            }).finally(function() {
                $('#loading').hide();
                $('#result').show();
            });
        }
    });

    $('#restart').on('click', function(e) {
        $('#builder').show();
        $('#result').hide();
    });

})(jQuery);